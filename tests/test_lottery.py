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


def test_lottery_endpoint_draws_and_records(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    login(client)
    r = client.post("/admin/activity/%d/lottery" % aid,
                    data={"count": "1", "exclude_winners": "on"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert len(d["round"]["winners"]) == 1
    assert d["round"]["excluded"] is True
    with app.app_context():
        assert LotteryRound.query.filter_by(activity_id=aid).count() == 1


def test_lottery_endpoint_requires_login(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code in (302, 401, 403)


def test_lottery_endpoint_without_candidates_fails(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    login(client)
    with app.app_context():
        before = LotteryRound.query.filter_by(activity_id=aid).count()
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False
    # 候选池为空时不得落任何轮次记录
    with app.app_context():
        assert LotteryRound.query.filter_by(activity_id=aid).count() == before


def test_lottery_read_endpoint_is_public(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client)
    client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    client.get("/logout")
    r = client.get("/api/activity/%d/lottery" % aid)
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["latest"]["winners"][0]["name"] == "张三"


def test_lottery_endpoint_forbidden_for_other_admin(client, app):
    """普通管理员对他人（超管）名下的活动抽签应 403，且不落轮次记录。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client, username="teacher2", password="teacher123456")
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code == 403
    with app.app_context():
        assert LotteryRound.query.filter_by(activity_id=aid).count() == 0


def test_lottery_read_endpoint_404_for_missing_activity(client):
    r = client.get("/api/activity/999999/lottery")
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_lottery_read_endpoint_hides_phone(client, app):
    """公开只读接口不得向匿名访问者暴露中奖人手机号。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    login(client)
    client.post("/admin/activity/%d/lottery" % aid, data={"count": "2"})
    client.get("/logout")
    r = client.get("/api/activity/%d/lottery" % aid)
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "phone" not in body
    assert "13800000001" not in body
    assert "13800000002" not in body
    d = r.get_json()
    assert d["ok"] is True
    for rnd in d["rounds"]:
        for w in rnd["winners"]:
            assert set(w.keys()) == {"name", "campus"}
    # 姓名与校区仍需保留，供大屏显示
    assert d["latest"]["winners"][0]["name"] in ("张三", "李四")


def test_lottery_endpoint_excludes_winners_by_default(client, app):
    """缺省即开启「排除已中奖」：服务端默认值独立于前端正确。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    login(client)
    r1 = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r1.status_code == 200
    d1 = r1.get_json()
    assert d1["round"]["excluded"] is True
    r2 = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r2.status_code == 200
    d2 = r2.get_json()
    assert d2["round"]["excluded"] is True
    # 第二轮不应再次抽中第一轮的人
    assert d1["round"]["winners"][0]["name"] != d2["round"]["winners"][0]["name"]


def test_lottery_endpoint_exclude_winners_can_be_disabled(client, app):
    """显式传关闭值时才不排除已中奖。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client)
    for off_value in ("0", "off", "false", "no"):
        r = client.post("/admin/activity/%d/lottery" % aid,
                        data={"count": "1", "exclude_winners": off_value})
        assert r.status_code == 200
        assert r.get_json()["round"]["excluded"] is False, \
            "exclude_winners={} 时应关闭排除".format(off_value)


def test_lottery_endpoint_records_actual_draw_count(client, app):
    """落库的 draw_count 是实际抽中人数，不是请求的人数。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    login(client)
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "5"})
    assert r.status_code == 200
    d = r.get_json()
    assert len(d["round"]["winners"]) == 2
    assert d["round"]["draw_count"] == 2
    with app.app_context():
        row = LotteryRound.query.filter_by(activity_id=aid).one()
        assert row.draw_count == 2


def test_lottery_endpoint_exclude_winners_uses_last_value(client, app):
    """同名多值（hidden + checkbox）时以最后一个取值为准，用户勾选意图不被静默反转。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    _signed_in(app, aid, "王五", "13800000003")
    login(client)

    # hidden(off) 在前、checkbox(on) 在后且已勾选 → 浏览器提交 "off&exclude_winners=on"
    # 用户明明勾上了「排除已中奖」，必须按排除执行
    r = client.post("/admin/activity/%d/lottery" % aid,
                    data={"count": "1", "exclude_winners": ["off", "on"]})
    assert r.status_code == 200
    assert r.get_json()["round"]["excluded"] is True

    # checkbox(on) 在前、hidden(off) 在后 → 以最后出现的取值为准
    r = client.post("/admin/activity/%d/lottery" % aid,
                    data={"count": "1", "exclude_winners": ["on", "off"]})
    assert r.status_code == 200
    assert r.get_json()["round"]["excluded"] is False

    # 字段缺失 → 缺省即排除
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code == 200
    assert r.get_json()["round"]["excluded"] is True

    # 显式 off → 允许重复中奖
    r = client.post("/admin/activity/%d/lottery" % aid,
                    data={"count": "1", "exclude_winners": "off"})
    assert r.status_code == 200
    assert r.get_json()["round"]["excluded"] is False


def test_lottery_read_endpoint_survives_malformed_winners(client, app):
    """脏数据（winners_json 元素非 dict）不得让公开接口 500。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    with app.app_context():
        dirty = LotteryRound(
            activity_id=aid, draw_count=1,
            winners_json='["oops"]', excluded=True, operator_id=None,
        )
        db.session.add(dirty)
        db.session.commit()
        dirty_id = dirty.id
    # 未登录的公开接口也必须扛得住脏数据
    r = client.get("/api/activity/%d/lottery" % aid)
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    for rnd in d["rounds"]:
        for w in rnd["winners"]:
            assert isinstance(w, dict)
            assert set(w.keys()) == {"name", "campus"}
    # 脏数据轮次本身仍返回，只是畸形元素被跳过
    dirty_round = [rnd for rnd in d["rounds"] if rnd["id"] == dirty_id]
    assert dirty_round and dirty_round[0]["winners"] == []


def test_lottery_endpoint_tolerates_malformed_history(client, app):
    """库里有畸形 winners_json 的旧轮次时，管理员仍可正常抽签（不得 500）。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    with app.app_context():
        db.session.add(LotteryRound(
            activity_id=aid, draw_count=1,
            winners_json='["oops"]', excluded=True, operator_id=None,
        ))
        db.session.commit()
    login(client)
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert len(d["round"]["winners"]) == 1
    assert d["round"]["winners"][0]["name"] == "张三"


def test_winner_items_keeps_only_dict_entries():
    """winner_items 只返回 dict 元素，脏数据被跳过。"""
    items = app_lottery.winner_items(
        ["oops", {"name": "张三", "campus": "敬慧路校区"}, None, 5, {"name": "李四"}])
    assert items == [
        {"name": "张三", "campus": "敬慧路校区"},
        {"name": "李四"},
    ]
    assert app_lottery.winner_items(None) == []
    assert app_lottery.winner_items([]) == []


def test_past_winner_keys_ignores_malformed_entries(app):
    """历史轮次含畸形中奖人时，past_winner_keys 不抛异常且只统计合法条目。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    with app.app_context():
        act = db.session.get(Activity, aid)
        app_lottery.save_round(
            act, [{"name": "张三", "campus": "敬慧路校区", "phone": "13800000001"}],
            1, True, None)
        db.session.add(LotteryRound(
            activity_id=aid, draw_count=1,
            winners_json='["oops"]', excluded=True, operator_id=None,
        ))
        db.session.commit()
        keys = app_lottery.past_winner_keys(act)
        assert keys == {app_lottery.person_key("张三", "敬慧路校区", "13800000001")}
