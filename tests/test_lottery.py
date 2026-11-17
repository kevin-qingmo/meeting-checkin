"""随机抽签与账号删除的测试。"""
import json
from datetime import datetime, timedelta

from app import lottery as app_lottery
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


def _not_signed_in(app, aid, name, phone, campus="敬慧路校区", source="scan"):
    """插入一条未签到记录（checked_in_at 为空），用于验证候选池过滤。

    注意：ORM 构造对象时 checked_in_at=None 仍会被列默认值 datetime.utcnow 覆盖，
    必须用 Core insert 显式写入 NULL 才能构造出「未签到」行。
    """
    with app.app_context():
        db.session.execute(db.insert(CheckIn).values(
            activity_id=aid, name=name, phone=phone, campus=campus,
            code_used="1234", mode="in", source=source,
            checked_in_at=None,
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


def test_candidate_pool_only_contains_signed_in(app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _not_signed_in(app, aid, "王五", "13800000003")
    with app.app_context():
        act = db.session.get(Activity, aid)
        pool = app_lottery.candidate_pool(act)
        names = [r.name for r in pool]
        assert names == ["张三"]
        assert "王五" not in names


def test_draw_only_from_signed_in(app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    _not_signed_in(app, aid, "王五", "13800000003")
    with app.app_context():
        act = db.session.get(Activity, aid)
        winners, available = app_lottery.draw(act, 5)
        assert available == 2
        assert len(winners) == 2
        assert {w["name"] for w in winners} == {"张三", "李四"}
        assert "王五" not in {w["name"] for w in winners}


def test_draw_excludes_previous_winners_when_flag_on(app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    with app.app_context():
        act = db.session.get(Activity, aid)
        winners, _ = app_lottery.draw(act, 1)
        app_lottery.save_round(act, winners, 1, True, None)
        second, available = app_lottery.draw(act, 1, exclude_winners=True)
        assert available == 1
        assert second[0]["name"] != winners[0]["name"]
        third, available3 = app_lottery.draw(act, 1, exclude_winners=False)
        assert available3 == 2


def test_person_key_prefers_phone():
    assert app_lottery.person_key("张三", "校区A", "13800000000") == "p:13800000000"
    assert app_lottery.person_key("张三", "校区A", "") == "n:张三|校区A"


def test_candidate_pool_dedupes_by_phone(app):
    """同一手机号两条签到记录 → 候选池只保留一条（去重键 p:<phone>）。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "张三", "13800000001", source="manual")
    with app.app_context():
        act = db.session.get(Activity, aid)
        pool = app_lottery.candidate_pool(act)
        assert len(pool) == 1
        assert pool[0].name == "张三"


def test_save_round_with_empty_winners_writes_nothing(app):
    """候选池为空时不落轮次记录：返回 None，且行数不增加。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    with app.app_context():
        act = db.session.get(Activity, aid)
        before = LotteryRound.query.filter_by(activity_id=aid).count()
        row = app_lottery.save_round(act, [], 1, True, None)
        assert row is None
        after = LotteryRound.query.filter_by(activity_id=aid).count()
        assert after == before


def test_save_round_stores_chinese_without_unicode_escape(app):
    """winners_json 原始文本直接含中文，不得被转义成 \\uXXXX。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    winners = [{"name": "张三", "campus": "敬慧路校区", "phone": "13800000001"}]
    with app.app_context():
        act = db.session.get(Activity, aid)
        row = app_lottery.save_round(act, winners, 1, True, None)
        db.session.expire_all()
        raw = db.session.get(LotteryRound, row.id).winners_json
        assert "张三" in raw
        assert "敬慧路校区" in raw
        assert "\\u" not in raw


def test_serialize_round_accepts_round_row_keyword(app):
    """serialize_round 的首参形参名为 round_row（brief Interfaces 约定）。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    with app.app_context():
        act = db.session.get(Activity, aid)
        row = app_lottery.save_round(
            act, [{"name": "张三", "campus": "敬慧路校区", "phone": "13800000001"}], 1, True, None)
        data = app_lottery.serialize_round(round_row=row, operator_name="教务主任")
        assert data["id"] == row.id
        assert data["draw_count"] == 1
        assert data["winners"][0]["name"] == "张三"
        assert data["excluded"] is True
        assert data["operator"] == "教务主任"
        assert data["created_at"]


def test_draw_count_below_one_or_invalid_draws_one(app):
    """count<=0 或非法值归一为 1（plan-mandated 行为，锁定不回归）。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    with app.app_context():
        act = db.session.get(Activity, aid)
        winners0, available0 = app_lottery.draw(act, 0)
        assert available0 == 2
        assert len(winners0) == 1

        winners_bad, available_bad = app_lottery.draw(act, "abc")
        assert available_bad == 2
        assert len(winners_bad) == 1
