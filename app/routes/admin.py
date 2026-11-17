import json
from datetime import datetime

from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)
from flask_login import current_user, login_required
from openpyxl import Workbook
from sqlalchemy.exc import IntegrityError

from ..access import (activity_stats, dict_campuses, dict_stages, dict_subjects,
                      get_managed_activity, live_payload, name_map)
from ..extensions import db
from ..lottery import candidate_pool, draw, recent_rounds, save_round, serialize_round
from ..models import (ALL_CAMPUS, Activity, CheckIn, LotteryRound, Roster, Setting,
                     User)
from ..roster import import_roster

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _parse_dt(raw, fallback=None):
    raw = (raw or "").strip()
    if not raw:
        return fallback
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return fallback


def _multi(form, field):
    return json.dumps([v for v in form.getlist(field) if v], ensure_ascii=False)


def _parse_uid(raw):
    """解析表单里的账号 id，非法值一律返回 None（不抛异常）。

    int() 对 '²' 等 Unicode 非十进制数字会抛 ValueError，未捕获会变成 500；
    所有按 id 取账号的分支都必须走这里，统一按「账号不存在」处理。
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _find_user(raw_uid):
    """按表单里的账号 id 取用户；id 非法或账号不存在一律返回 None。"""
    uid = _parse_uid(raw_uid)
    if uid is None:
        return None
    return db.session.get(User, uid)


@bp.route("/")
@login_required
def activities():
    q = Activity.query
    if not current_user.is_super:
        q = q.filter_by(owner_id=current_user.id)
    items = q.order_by(Activity.created_at.desc()).all()
    rows = []
    for a in items:
        st = activity_stats(a)
        rows.append({"activity": a, "stats": st})
    return render_template("admin/activities.html", rows=rows)


@bp.route("/activity/new", methods=["GET", "POST"])
@login_required
def activity_new():
    if request.method == "POST":
        data, error = _read_form(request.form)
        if error:
            flash(error, "error")
        else:
            data["owner_id"] = current_user.id
            act = Activity(**data)
            db.session.add(act)
            db.session.commit()
            flash("活动已创建", "success")
            return redirect(url_for("admin.dashboard", activity_id=act.id))
    return render_template(
        "admin/activity_form.html",
        activity=None,
        campuses=dict_campuses(),
        stages=dict_stages(),
        subjects=dict_subjects(),
    )


@bp.route("/activity/<int:activity_id>/edit", methods=["GET", "POST"])
@login_required
def activity_edit(activity_id):
    act = get_managed_activity(activity_id)
    if request.method == "POST":
        data, error = _read_form(request.form)
        if error:
            flash(error, "error")
        else:
            for k, v in data.items():
                setattr(act, k, v)
            db.session.commit()
            flash("活动已更新", "success")
            return redirect(url_for("admin.dashboard", activity_id=act.id))
    return render_template(
        "admin/activity_form.html",
        activity=act,
        campuses=dict_campuses(),
        stages=dict_stages(),
        subjects=dict_subjects(),
    )


def _read_form(form):
    title = (form.get("title") or "").strip()
    if not title:
        return None, "请填写活动名称"
    start_at = _parse_dt(form.get("start_at"))
    end_at = _parse_dt(form.get("end_at"))
    if not start_at:
        return None, "请填写活动开始时间"
    if not end_at:
        return None, "请填写活动结束时间"
    if end_at <= start_at:
        return None, "结束时间必须晚于开始时间"
    # 「全校活动」：覆盖全部校区，学段/学科不参与筛选
    if form.get("school_wide") in ("on", "1", "true", "yes"):
        campus_ids = json.dumps([ALL_CAMPUS], ensure_ascii=False)
        stage_ids = "[]"
        subject_ids = "[]"
    else:
        campus_ids = _multi(form, "campus_ids")
        stage_ids = _multi(form, "stage_ids")
        subject_ids = _multi(form, "subject_ids")
    return {
        "title": title,
        "campus_ids": campus_ids,
        "stage_ids": stage_ids,
        "subject_ids": subject_ids,
        "start_at": start_at,
        "end_at": end_at,
        "location": (form.get("location") or "").strip(),
        "need_checkout": form.get("need_checkout") == "on",
    }, None


@bp.route("/activity/<int:activity_id>/archive", methods=["POST"])
@login_required
def activity_archive(activity_id):
    act = get_managed_activity(activity_id)
    act.status = "archived" if act.status == "active" else "active"
    db.session.commit()
    flash("已归档" if act.status == "archived" else "已恢复", "success")
    return redirect(url_for("admin.activities"))


@bp.route("/activity/<int:activity_id>/delete", methods=["POST"])
@login_required
def activity_delete(activity_id):
    """彻底删除活动（含名册与全部签到记录，不可恢复）。"""
    act = get_managed_activity(activity_id)
    title = act.title
    # 按依赖顺序清理：抽签轮次 → 签到 → 名册 → 活动
    # （LotteryRound.activity_id 是 NOT NULL 外键，不先删轮次会 IntegrityError 500）
    LotteryRound.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    CheckIn.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    Roster.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    db.session.delete(act)
    db.session.commit()
    flash("已删除活动「{}」".format(title), "success")
    return redirect(url_for("admin.activities"))


def _exclude_winners_flag(values):
    """判定「排除已中奖」开关：默认开启，仅显式传关闭值时才关闭。

    values：表单里 exclude_winners 的全部取值（可能多个，如 hidden + checkbox 同名）。
    同名多值时以**最后一个**为准 —— 浏览器按 DOM 顺序提交，checkbox 在后则其值在后，
    这样 hidden(off) + checkbox(on) 勾选时按「排除」执行，勾选意图不会被静默反转。

    判定表：
      字段缺失（空列表 / None） → True（缺省排除）
      "" / 纯空白              → True（视为缺省）
      on / 1 / true / yes      → True
      0 / off / false / no     → False（显式关闭）
      其它任意值               → True（默认排除，fail-safe）
    """
    if not values:
        return True
    value = str(values[-1]).strip().lower()
    if not value:
        return True
    return value not in ("0", "off", "false", "no")


@bp.route("/activity/<int:activity_id>/lottery", methods=["POST"])
@login_required
def activity_lottery(activity_id):
    """从已签到人员中随机抽签并留痕。"""
    act = get_managed_activity(activity_id)
    try:
        count = int(request.form.get("count") or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, count)
    exclude = _exclude_winners_flag(request.form.getlist("exclude_winners"))
    if not candidate_pool(act):
        return jsonify({"ok": False, "message": "暂无可抽取人员，请先完成签到"}), 400
    winners, available = draw(act, count, exclude)
    if not winners:
        return jsonify({
            "ok": False,
            "message": "可抽取人员不足（可抽 {} 人）".format(available),
        }), 400
    # draw_count 记录实际抽中人数（请求人数可能大于可抽人数）
    row = save_round(act, winners, len(winners), exclude, current_user.id)
    if row is None:
        # 兜底：save_round 在中奖人为空时不落库
        return jsonify({"ok": False, "message": "暂无可抽取人员，请先完成签到"}), 400
    return jsonify({
        "ok": True,
        "message": "已抽出 {} 人".format(len(winners)),
        "round": serialize_round(row, current_user.display_name),
        "rounds": recent_rounds(act, 5),
    })


@bp.route("/activity/<int:activity_id>/roster", methods=["POST"])
@login_required
def roster_import(activity_id):
    act = get_managed_activity(activity_id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash("请选择要导入的 Excel 文件", "error")
        return redirect(url_for("admin.dashboard", activity_id=act.id))
    try:
        added, errors = import_roster(act.id, f)
    except Exception as exc:  # noqa: BLE001
        flash("导入失败：{}".format(exc), "error")
        return redirect(url_for("admin.dashboard", activity_id=act.id))
    if added:
        flash("成功导入 {} 条名册".format(added), "success")
    else:
        flash("没有导入任何记录，请检查表格格式", "error")
    if errors:
        flash("跳过 {} 行（姓名或校区为空）：{}".format(len(errors), "、".join(errors[:5])), "warning")
    return redirect(url_for("admin.dashboard", activity_id=act.id))


@bp.route("/activity/<int:activity_id>/roster_template")
@login_required
def roster_template(activity_id):
    get_managed_activity(activity_id)
    wb = Workbook()
    ws = wb.active
    ws.title = "名册"
    ws.append(["姓名", "校区", "手机号", "学段", "学科"])
    ws.append(["张三", "敬慧路校区", "13800000000", "初中", "语文"])
    ws.append(["李四", "和慧南路校区", "", "初中", "数学"])
    bio = __import__("io").BytesIO()
    wb.save(bio)
    bio.seek(0)
    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="名册导入模板.xlsx",
    )


@bp.route("/activity/<int:activity_id>/dashboard")
@login_required
def dashboard(activity_id):
    act = get_managed_activity(activity_id)
    return render_template(
        "admin/dashboard.html",
        activity=act,
        campuses=dict_campuses(),
        stats=activity_stats(act),
        live=live_payload(act),
    )


@bp.route("/activity/<int:activity_id>/export")
@login_required
def export(activity_id):
    act = get_managed_activity(activity_id)
    from ..exporter import build_workbook
    bio = __import__("io").BytesIO()
    build_workbook(act).save(bio)
    bio.seek(0)
    fname = "签到表_{}_{}.xlsx".format(act.title, act.start_at.strftime("%Y%m%d"))
    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=fname,
    )


@bp.route("/users", methods=["GET", "POST"])
@login_required
def users():
    if not current_user.is_super:
        abort(403)
    if request.method == "POST":
        action = request.form.get("action")
        if action == "create":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            display_name = (request.form.get("display_name") or "").strip() or username
            if not username or len(password) < 6:
                flash("用户名不能为空，密码至少 6 位", "error")
            elif User.query.filter_by(username=username).first():
                flash("用户名已存在", "error")
            else:
                u = User(username=username, display_name=display_name, role="admin")
                u.set_password(password)
                db.session.add(u)
                db.session.commit()
                flash("账号已创建", "success")
        elif action == "toggle":
            u = _find_user(request.form.get("uid"))
            if u is None:
                flash("账号不存在", "error")
            elif u.id != current_user.id:
                u.active = not u.active
                db.session.commit()
                flash("已更新账号状态", "success")
        elif action == "reset":
            password = request.form.get("password") or ""
            u = _find_user(request.form.get("uid"))
            if u is None:
                flash("账号不存在", "error")
            elif len(password) >= 6:
                u.set_password(password)
                db.session.commit()
                flash("密码已重置", "success")
            else:
                flash("密码至少 6 位", "error")
        elif action == "role":
            u = _find_user(request.form.get("uid"))
            if u is None:
                flash("账号不存在", "error")
            elif u.id != current_user.id:
                u.role = "super" if u.role != "super" else "admin"
                db.session.commit()
                flash("已更新角色", "success")
        elif action == "rename":
            display_name = (request.form.get("display_name") or "").strip()
            u = _find_user(request.form.get("uid"))
            if u is None:
                flash("账号不存在", "error")
            elif display_name:
                u.display_name = display_name
                db.session.commit()
                flash("姓名已更新", "success")
            else:
                flash("请填写姓名", "error")
        elif action == "delete":
            # 非法参数必须兜住（见 _parse_uid）：一律按「账号不存在」处理
            u = _find_user(request.form.get("uid"))
            if u is None:
                flash("账号不存在", "error")
            elif u.id == current_user.id:
                flash("不能删除当前登录的账号", "error")
            elif u.is_super:
                # 删除能力限定在普通管理员；创建者账号不可被删除
                flash("不能删除创建者账号", "error")
            else:
                try:
                    name = u.display_name
                    # 只取 id，避免把活动实体挂进会话（避免 ORM 级联空外键）
                    act_ids = [row[0] for row in
                               db.session.query(Activity.id).filter(Activity.owner_id == u.id).all()]
                    # 先解除该账号在别处留下的「操作人」引用：
                    # CheckIn.operator_id 无 ondelete；LotteryRound.operator_id 虽有
                    # ON DELETE SET NULL，但本地 SQLite 不执行外键，且 ORM 也不会自动置空，
                    # 因此两处都必须在代码里显式置空，生产 Postgres 同样安全。
                    CheckIn.query.filter(CheckIn.operator_id == u.id).update(
                        {CheckIn.operator_id: None}, synchronize_session=False)
                    LotteryRound.query.filter(LotteryRound.operator_id == u.id).update(
                        {LotteryRound.operator_id: None}, synchronize_session=False)
                    # 名下的活动按依赖顺序删除：轮次 → 签到 → 名册 → 活动
                    # （Activity.owner_id 是 NOT NULL 外键，必须先删活动再删用户）
                    if act_ids:
                        LotteryRound.query.filter(
                            LotteryRound.activity_id.in_(act_ids)).delete(synchronize_session=False)
                        CheckIn.query.filter(
                            CheckIn.activity_id.in_(act_ids)).delete(synchronize_session=False)
                        Roster.query.filter(
                            Roster.activity_id.in_(act_ids)).delete(synchronize_session=False)
                        Activity.query.filter(
                            Activity.id.in_(act_ids)).delete(synchronize_session=False)
                    db.session.delete(u)
                    db.session.commit()
                except IntegrityError:
                    # 外键冲突等：回滚整笔操作，不留半删，给出中文提示
                    db.session.rollback()
                    flash("删除失败，请稍后重试", "error")
                else:
                    if act_ids:
                        flash("已删除账号「{}」及其 {} 个活动".format(name, len(act_ids)), "success")
                    else:
                        flash("已删除账号「{}」".format(name), "success")
    return render_template("admin/users.html", users=User.query.order_by(User.id).all())


@bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    if not current_user.is_super:
        abort(403)
    if request.method == "POST":
        for key in ("campuses", "stages", "subjects"):
            raw = request.form.get(key) or ""
            items = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                ident = "x{}".format(abs(hash(line)) % 100000)
                items.append({"id": ident, "name": line})
            Setting.set_list(key, items)
        db.session.commit()
        flash("字典已保存", "success")
    return render_template(
        "admin/settings.html",
        campuses=dict_campuses(),
        stages=dict_stages(),
        subjects=dict_subjects(),
    )
