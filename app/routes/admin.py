import json
from datetime import datetime

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   send_file, url_for)
from flask_login import current_user, login_required
from openpyxl import Workbook

from ..access import (activity_stats, dict_campuses, dict_stages, dict_subjects,
                      get_managed_activity, live_payload, name_map)
from ..extensions import db
from ..models import Activity, CheckIn, Roster, Setting, User
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
    return {
        "title": title,
        "campus_ids": _multi(form, "campus_ids"),
        "stage_ids": _multi(form, "stage_ids"),
        "subject_ids": _multi(form, "subject_ids"),
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
    CheckIn.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    Roster.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    db.session.delete(act)
    db.session.commit()
    flash("已删除活动「{}」".format(title), "success")
    return redirect(url_for("admin.activities"))


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
            uid = request.form.get("uid")
            u = db.session.get(User, int(uid)) if uid else None
            if u and u.id != current_user.id:
                u.active = not u.active
                db.session.commit()
                flash("已更新账号状态", "success")
        elif action == "reset":
            uid = request.form.get("uid")
            password = request.form.get("password") or ""
            u = db.session.get(User, int(uid)) if uid else None
            if u and len(password) >= 6:
                u.set_password(password)
                db.session.commit()
                flash("密码已重置", "success")
            else:
                flash("密码至少 6 位", "error")
        elif action == "role":
            uid = request.form.get("uid")
            u = db.session.get(User, int(uid)) if uid else None
            if u and u.id != current_user.id:
                u.role = "super" if u.role != "super" else "admin"
                db.session.commit()
                flash("已更新角色", "success")
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
