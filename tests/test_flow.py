"""验收测试：覆盖设计文档第 9 节的 6 条验收标准。"""
from datetime import datetime, timedelta

from app.codes import current_cycle, make_site_code, make_token, verify
from app.extensions import db
from app.models import Activity, CheckIn, Roster, User
from conftest import login


# ---------- 1. 码生成与校验 ----------
def test_code_rotates_every_cycle():
    c = current_cycle()
    assert make_token(1, c) == make_token(1, c)
    assert make_token(1, c) != make_token(1, c + 1)
    assert len(make_site_code(1, c)) == 4


def test_verify_accepts_current_and_previous_cycle():
    c = current_cycle()
    ok, _ = verify(1, make_token(1, c), make_site_code(1, c), c)
    assert ok
    ok, _ = verify(1, make_token(1, c - 1), make_site_code(1, c - 1), c - 1)
    assert ok
    ok, msg = verify(1, make_token(1, c - 5), make_site_code(1, c - 5), c - 5)
    assert not ok and "刷新" in msg


def test_verify_rejects_wrong_site_code():
    c = current_cycle()
    ok, msg = verify(1, make_token(1, c), "0000", c)
    assert not ok and "现场码" in msg


# ---------- 2. 认证与权限 ----------
def test_login_success_and_logout(client):
    r = login(client)
    assert "活动管理" in r.get_data(as_text=True)
    r = client.get("/logout", follow_redirects=True)
    assert "请先登录" in r.get_data(as_text=True) or "登录" in r.get_data(as_text=True)


def test_login_wrong_password(client):
    r = client.post("/login", data={"username": "admin", "password": "bad"},
                    follow_redirects=True)
    assert "用户名或密码错误" in r.get_data(as_text=True)


def test_normal_admin_cannot_see_others_activity(client, app):
    login(client, "teacher2", "teacher123456")
    r = client.get("/admin/")
    assert "小学语文骨干研修班研修活动" not in r.get_data(as_text=True)


def test_normal_admin_cannot_open_users_page(client):
    login(client, "teacher2", "teacher123456")
    r = client.get("/admin/users")
    assert r.status_code == 403


def test_super_admin_can_open_users_page(client):
    login(client)
    assert client.get("/admin/users").status_code == 200


# ---------- 3. 活动管理 ----------
def test_create_activity_with_multi_select(client, app):
    login(client)
    data = {
        "title": "初中化学展课",
        "campus_ids": ["敬慧路校区", "雅馨路校区"],
        "stage_ids": ["初中"],
        "subject_ids": ["化学", "物理"],
        "start_at": "2026-11-20T08:30",
        "end_at": "2026-11-20T11:30",
        "location": "昭慧路校区 伯苓楼",
        "need_checkout": "on",
    }
    r = client.post("/admin/activity/new", data=data, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        act = Activity.query.filter_by(title="初中化学展课").one()
        assert act.campuses == ["敬慧路校区", "雅馨路校区"]
        assert act.subjects == ["化学", "物理"]
        assert act.need_checkout is True


def test_activity_form_rejects_bad_time(client):
    login(client)
    r = client.post("/admin/activity/new", data={
        "title": "时间错误活动",
        "start_at": "2026-11-20T11:30",
        "end_at": "2026-11-20T08:30",
    }, follow_redirects=True)
    assert "结束时间必须晚于开始时间" in r.get_data(as_text=True)


# ---------- 4. 名册导入 ----------
def _make_xlsx(path, rows):
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    wb.save(path)
    return path


def test_import_roster_and_absent_list(client, app, tmp_path):
    login(client)
    p = tmp_path / "roster.xlsx"
    _make_xlsx(p, [
        ["姓名", "校区", "手机号", "学段", "学科"],
        ["张三", "敬慧路校区", "13800000001", "初中", "语文"],
        ["李四", "雅馨路校区", "13800000002", "初中", "语文"],
        ["", "", "", "", ""],
    ])
    with open(p, "rb") as f:
        r = client.post("/admin/activity/%d/roster" % app.config["TEST_ACTIVITY_ID"],
                        data={"file": (f, "roster.xlsx")},
                        content_type="multipart/form-data", follow_redirects=True)
    body = r.get_data(as_text=True)
    assert "成功导入 2 条名册" in body
    with app.app_context():
        assert Roster.query.count() == 2


def test_roster_template_download(client, app):
    login(client)
    r = client.get("/admin/activity/%d/roster_template" % app.config["TEST_ACTIVITY_ID"])
    assert r.status_code == 200
    assert b"spreadsheetml" in r.headers["Content-Type"].encode()


# ---------- 5. 扫码签到 / 签离 ----------
def _scan(client, app, name="张三", phone="13800000000", campus="敬慧路校区",
          site_code=None, cycle=None, mode="in"):
    with app.app_context():
        act_id = app.config["TEST_ACTIVITY_ID"]
        c = current_cycle() if cycle is None else cycle
        code = site_code if site_code is not None else make_site_code(act_id, c, mode)
        token = make_token(act_id, c, mode)
    return client.post("/api/scan/%d" % act_id, data={
        "name": name, "phone": phone, "campus": campus,
        "site_code": code, "token": token, "cycle": str(c), "mode": mode,
    }, headers={"X-Requested-With": "XMLHttpRequest"})


def test_scan_wrong_site_code_rejected(client, app):
    r = _scan(client, app, site_code="0000")
    assert "现场码不正确" in r.get_data(as_text=True)


def test_scan_correct_code_success(client, app):
    r = _scan(client, app)
    assert "签到成功" in r.get_data(as_text=True)
    with app.app_context():
        assert CheckIn.query.count() == 1


def test_scan_duplicate_phone_not_counted_twice(client, app):
    _scan(client, app)
    r = _scan(client, app)
    assert "请勿重复签到" in r.get_data(as_text=True)
    with app.app_context():
        assert CheckIn.query.count() == 1


def test_checkout_updates_record(client, app):
    _scan(client, app)
    r = _scan(client, app, mode="out")
    assert "签离成功" in r.get_data(as_text=True)
    with app.app_context():
        rec = CheckIn.query.one()
        assert rec.checked_out_at is not None


def test_checkout_without_checkin_fails(client, app):
    r = _scan(client, app, phone="13999999999", mode="out")
    assert "未找到您的签到记录" in r.get_data(as_text=True)


def test_scan_outside_time_window_rejected(client, app):
    with app.app_context():
        act = db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])
        act.start_at = datetime.now() + timedelta(days=1)
        act.end_at = datetime.now() + timedelta(days=2)
        db.session.commit()
    r = _scan(client, app)
    assert "签到未开始" in r.get_data(as_text=True)


# ---------- 6. 大屏与实时数据 ----------
def test_board_qr_endpoint(client, app):
    login(client)
    r = client.get("/api/board/%d/qr" % app.config["TEST_ACTIVITY_ID"])
    assert r.status_code == 200
    d = r.get_json()
    assert len(d["site_code"]) == 4
    assert d["cycle_seconds"] == 20
    assert d["qr_png"].endswith(".png?cycle=%d&mode=in" % d["cycle"])


def test_board_png_is_png(client, app):
    login(client)
    r = client.get("/qr/%d.png" % app.config["TEST_ACTIVITY_ID"])
    assert r.status_code == 200
    assert r.headers["Content-Type"] == "image/png"
    assert r.data[:4] == b"\x89PNG"


def test_board_page_renders(client, app):
    login(client)
    r = client.get("/board/%d" % app.config["TEST_ACTIVITY_ID"])
    body = r.get_data(as_text=True)
    assert "现场码" in body and "最新动态" in body and "切换为签离模式" in body


def test_live_api_counts(client, app):
    login(client)
    _scan(client, app)
    r = client.get("/api/activity/%d/live" % app.config["TEST_ACTIVITY_ID"])
    d = r.get_json()
    assert d["checked_in"] == 1
    assert d["checked_out"] == 0
    assert d["records"][0]["name"] == "张三"


# ---------- 7. 补录与导出 ----------
def test_manual_checkin(client, app):
    login(client)
    r = client.post("/api/activity/%d/manual" % app.config["TEST_ACTIVITY_ID"], data={
        "name": "补录同学", "phone": "13700000000", "campus": "和慧南路校区",
    })
    assert r.get_json()["ok"] is True
    with app.app_context():
        rec = CheckIn.query.filter_by(name="补录同学").one()
        assert rec.source == "manual"


def test_export_excel_has_three_sheets(client, app):
    login(client)
    _scan(client, app)
    r = client.get("/admin/activity/%d/export" % app.config["TEST_ACTIVITY_ID"])
    assert r.status_code == 200
    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["签到明细", "应到实到统计", "缺席名单"]


def test_delete_checkin(client, app):
    login(client)
    _scan(client, app)
    with app.app_context():
        cid = CheckIn.query.one().id
    r = client.post("/api/checkin/%d/delete" % cid)
    assert r.get_json()["ok"] is True
    with app.app_context():
        assert CheckIn.query.count() == 0


# ---------- 8. 删除活动 ----------
def test_delete_activity_removes_roster_and_checkins(client, app):
    login(client)
    aid = app.config["TEST_ACTIVITY_ID"]
    _scan(client, app)
    with app.app_context():
        db.session.add(Roster(activity_id=aid, name="李四", campus="敬慧路校区"))
        db.session.commit()
        assert Roster.query.filter_by(activity_id=aid).count() == 1
    r = client.post("/admin/activity/%d/delete" % aid, follow_redirects=True)
    assert "已删除活动" in r.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Activity, aid) is None
        assert CheckIn.query.filter_by(activity_id=aid).count() == 0
        assert Roster.query.filter_by(activity_id=aid).count() == 0


def test_deleted_activity_pages_return_404(client, app):
    login(client)
    aid = app.config["TEST_ACTIVITY_ID"]
    client.post("/admin/activity/%d/delete" % aid)
    assert client.get("/board/%d" % aid).status_code == 404
    assert client.get("/scan/%d" % aid).status_code == 404
    assert client.get("/api/activity/%d/live" % aid).status_code == 404


def test_delete_activity_permission_checked(client, app):
    """普通管理员不能删除别人的活动。"""
    login(client, "teacher2", "teacher123456")
    r = client.post("/admin/activity/%d/delete" % app.config["TEST_ACTIVITY_ID"])
    assert r.status_code == 403
    with app.app_context():
        assert db.session.get(Activity, app.config["TEST_ACTIVITY_ID"]) is not None


def test_activities_page_has_delete_button(client, app):
    login(client)
    body = client.get("/admin/").get_data(as_text=True)
    assert "/delete" in body and "确定删除活动" in body


# ---------- 9. 切换签到/签离模式换码 ----------
def test_mode_switch_returns_different_code(client, app):
    login(client)
    aid = app.config["TEST_ACTIVITY_ID"]
    d_in = client.get("/api/board/%d/qr?mode=in" % aid).get_json()
    d_out = client.get("/api/board/%d/qr?mode=out" % aid).get_json()
    assert d_in["token"] != d_out["token"]
    assert d_in["site_code"] != d_out["site_code"]
    assert d_in["qr_url"].endswith("m=in")
    assert d_out["qr_url"].endswith("m=out")
    assert d_out["qr_png"].endswith("mode=out")


def test_code_of_other_mode_is_rejected(client, app):
    """签离模式的码不能拿去签到（反截图转发）。"""
    aid = app.config["TEST_ACTIVITY_ID"]
    with app.app_context():
        c = current_cycle()
        token = make_token(aid, c, "out")
        code = make_site_code(aid, c, "out")
    r = client.post("/api/scan/%d" % aid, data={
        "name": "张三", "phone": "13800000000", "campus": "敬慧路校区",
        "site_code": code, "token": token, "cycle": str(c), "mode": "in",
    }, headers={"X-Requested-With": "XMLHttpRequest"})
    assert "签到码无效" in r.get_data(as_text=True)


def test_checkout_uses_its_own_code(client, app):
    """签离流程使用签离模式自己的码。"""
    _scan(client, app)
    r = _scan(client, app, mode="out")
    assert "签离成功" in r.get_data(as_text=True)


# ---------- 10. 「全校活动」选项 ----------
def test_school_wide_option_exists_in_form(client):
    login(client)
    body = client.get("/admin/activity/new").get_data(as_text=True)
    assert "全校活动" in body
    assert 'name="school_wide"' in body


def test_school_wide_saves_all_campus_and_clears_stage_subject(client, app):
    """勾选全校活动 → 校区记为全校活动，学段/学科清空。"""
    login(client)
    r = client.post("/admin/activity/new", data={
        "title": "全校教师大会",
        "school_wide": "1",
        "campus_ids": ["敬慧路校区"],
        "stage_ids": ["初中"],
        "subject_ids": ["语文"],
        "start_at": "2026-11-20T08:30",
        "end_at": "2026-11-20T11:30",
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        act = Activity.query.filter_by(title="全校教师大会").one()
        assert act.is_school_wide is True
        assert act.campuses == ["全校活动"]
        assert act.stages == []
        assert act.subjects == []


def test_school_wide_edit_form_marks_checked_and_disables(client, app):
    """编辑全校活动时：复选框选中，学段/学科输入框禁用。"""
    login(client)
    client.post("/admin/activity/new", data={
        "title": "全校教研活动",
        "school_wide": "1",
        "start_at": "2026-11-20T08:30",
        "end_at": "2026-11-20T11:30",
    }, follow_redirects=True)
    with app.app_context():
        aid = Activity.query.filter_by(title="全校教研活动").one().id
    body = client.get("/admin/activity/%d/edit" % aid).get_data(as_text=True)
    assert "全校活动" in body
    assert "disabled" in body


def test_normal_activity_keeps_stage_subject(client, app):
    """未勾选全校活动时，学段/学科照常保存。"""
    login(client)
    client.post("/admin/activity/new", data={
        "title": "普通校区活动",
        "campus_ids": ["和慧南路校区"],
        "stage_ids": ["初中"],
        "subject_ids": ["物理"],
        "start_at": "2026-11-20T08:30",
        "end_at": "2026-11-20T11:30",
    }, follow_redirects=True)
    with app.app_context():
        act = Activity.query.filter_by(title="普通校区活动").one()
        assert act.is_school_wide is False
        assert act.campuses == ["和慧南路校区"]
        assert act.stages == ["初中"]
        assert act.subjects == ["物理"]
