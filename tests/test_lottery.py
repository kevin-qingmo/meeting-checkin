"""随机抽签与账号删除的测试。"""
import json
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Activity, CheckIn, LotteryRound, Roster, User
from conftest import login
from sqlalchemy.schema import CreateTable


def _signed_in(app, aid, name, phone, campus="敬慧路校区", source="scan"):
    with app.app_context():
        db.session.add(CheckIn(
            activity_id=aid, name=name, phone=phone, campus=campus,
            code_used="1234", mode="in", source=source,
            checked_in_at=datetime.now(),
        ))
        db.session.commit()


def _enable_sqlite_foreign_keys(engine):
    """本地 SQLite 默认关闭外键约束（生产 Postgres 始终强制执行）。

    显式开启后，SQLite 的 ON DELETE 行为与 Postgres 一致，
    用于验证生产环境的外键兜底语义。
    """
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA foreign_keys")
        enabled = cur.fetchone()[0]
    finally:
        conn.close()
    assert enabled == 1, "无法开启 SQLite 外键约束"


def test_lottery_round_model_roundtrip(app):
    with app.app_context():
        act = db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])
        admin = User.query.filter_by(username="admin").one()
        rnd = LotteryRound(
            activity_id=act.id, draw_count=2,
            winners_json=json.dumps([{"name": "张三", "campus": "敬慧路校区", "phone": "13800000000"}],
                                     ensure_ascii=False),
            excluded=True, operator_id=admin.id,
        )
        db.session.add(rnd)
        db.session.commit()
        assert rnd.id is not None
        assert rnd.winners[0]["name"] == "张三"
        assert rnd.excluded is True
        assert len(act.lottery_rounds) == 1


def test_lottery_round_operator_relationship(app):
    """operator 关系可取到用户，且 display_name 正确（Task 2 recent_rounds 依赖）。"""
    with app.app_context():
        act = db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])
        admin = User.query.filter_by(username="admin").one()
        rnd = LotteryRound(
            activity_id=act.id, draw_count=1, winners_json="[]",
            excluded=True, operator_id=admin.id,
        )
        db.session.add(rnd)
        db.session.commit()
        db.session.expire_all()

        row = db.session.get(LotteryRound, rnd.id)
        assert row.operator is not None
        assert row.operator.id == admin.id
        assert row.operator.username == "admin"
        assert row.operator.display_name == "教务主任"


def test_lottery_round_winners_non_list_json_returns_empty(app):
    """合法但非列表的 JSON（null / 字符串 / 数字）一律返回 []，避免调用方遍历时报错。"""
    with app.app_context():
        act = db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])
        for raw in ("null", '"张三"', "123", "not-json"):
            rnd = LotteryRound(
                activity_id=act.id, draw_count=1, winners_json=raw,
                excluded=True, operator_id=None,
            )
            db.session.add(rnd)
            db.session.commit()
            assert rnd.winners == [], f"winners_json={raw!r} 时应返回 []"


def test_lottery_round_operator_fk_set_null_when_user_deleted(app):
    """删除操作人账号后，其参与的抽签轮次不残留悬空引用（外键 ON DELETE SET NULL）。"""
    with app.app_context():
        act = db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])
        operator = User.query.filter_by(username="teacher2").one()
        rnd = LotteryRound(
            activity_id=act.id, draw_count=1, winners_json="[]",
            excluded=True, operator_id=operator.id,
        )
        db.session.add(rnd)
        db.session.commit()

        # 外键定义本身必须带 ON DELETE SET NULL（生产 Postgres 依赖它兜底）
        fk = list(LotteryRound.__table__.c.operator_id.foreign_keys)[0]
        assert fk.ondelete == "SET NULL"
        ddl = str(CreateTable(LotteryRound.__table__).compile(dialect=db.engine.dialect))
        assert "ON DELETE SET NULL" in ddl

        # 本地 SQLite 默认不执行外键，显式开启后复现生产语义
        _enable_sqlite_foreign_keys(db.engine)

        db.session.delete(operator)
        db.session.commit()
        db.session.expire_all()

        row = db.session.get(LotteryRound, rnd.id)
        assert row is not None
        assert row.operator_id is None
        assert row.operator is None

        # 不得残留指向已删除账号的引用
        dangling = db.session.query(LotteryRound).filter(
            LotteryRound.operator_id.isnot(None),
            ~db.session.query(User.id).filter(User.id == LotteryRound.operator_id).exists(),
        ).count()
        assert dangling == 0
