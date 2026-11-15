from datetime import datetime

from flask import (Blueprint, jsonify, render_template, request)

from ..access import activity_status, dict_campuses
from ..codes import verify
from ..extensions import db
from ..models import Activity, CheckIn

bp = Blueprint("scan", __name__)


def _wants_json():
    return request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"


def _context(activity, mode="in"):
    return {
        "activity": activity,
        "mode": mode,
        "token": request.args.get("t") or request.form.get("token") or "",
        "cycle": request.args.get("c") or request.form.get("cycle") or "",
        "campuses": dict_campuses(),
        "status": activity_status(activity),
    }


@bp.route("/scan/<int:activity_id>", methods=["GET"])
def form(activity_id):
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        return render_template("error.html", code=404, message="活动不存在"), 404
    mode = request.args.get("m", "in")
    if mode not in ("in", "out"):
        mode = "in"
    return render_template("scan.html", **_context(activity, mode))


@bp.route("/api/scan/<int:activity_id>", methods=["POST"])
def submit(activity_id):
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        msg = "活动不存在"
        if _wants_json():
            return jsonify({"ok": False, "message": msg}), 404
        return render_template("error.html", code=404, message=msg), 404

    name = (request.form.get("name") or request.form.get("姓名") or "").strip()
    phone = (request.form.get("phone") or request.form.get("手机号") or "").strip()
    campus = (request.form.get("campus") or request.form.get("校区") or "").strip()
    site_code = (request.form.get("site_code") or request.form.get("现场码") or "").strip()
    token = request.form.get("token") or ""
    cycle = request.form.get("cycle") or ""
    mode = request.form.get("mode") or "in"
    if mode not in ("in", "out"):
        mode = "in"

    def fail(msg, code=200):
        if _wants_json():
            return jsonify({"ok": False, "message": msg}), code
        ctx = _context(activity, mode)
        ctx.update({"message": msg, "ok": False})
        return render_template("scan.html", **ctx), code

    if not name:
        return fail("请填写姓名")
    if not campus:
        return fail("请选择校区")
    if not phone:
        return fail("请填写手机号")

    status = activity_status(activity)
    if status == "not_started":
        return fail("签到未开始，活动时间为 {}".format(activity.start_at.strftime("%Y-%m-%d %H:%M")))
    if status == "ended":
        return fail("签到已结束，如需补签请联系管理员")

    ok, why = verify(activity.id, token, site_code, cycle)
    if not ok:
        return fail(why)

    now = datetime.now()

    if mode == "out":
        record = None
        if phone:
            record = (
                CheckIn.query.filter(
                    CheckIn.activity_id == activity.id,
                    CheckIn.phone == phone,
                    CheckIn.mode == "in",
                    CheckIn.checked_out_at.is_(None),
                )
                .order_by(CheckIn.checked_in_at.desc())
                .first()
            )
        if record is None:
            record = (
                CheckIn.query.filter(
                    CheckIn.activity_id == activity.id,
                    CheckIn.name == name,
                    CheckIn.mode == "in",
                    CheckIn.checked_out_at.is_(None),
                )
                .order_by(CheckIn.checked_in_at.desc())
                .first()
            )
        if record is None:
            return fail("未找到您的签到记录，请确认姓名/手机号是否与签到时一致")
        record.checked_out_at = now
        db.session.commit()
        msg = "签离成功，签到时间 {}".format(
            record.checked_in_at.strftime("%H:%M:%S") if record.checked_in_at else "-")
        if _wants_json():
            return jsonify({"ok": True, "message": msg})
        ctx = _context(activity, mode)
        ctx.update({"message": msg, "ok": True})
        return render_template("scan.html", **ctx)

    existing = (
        CheckIn.query.filter(
            CheckIn.activity_id == activity.id,
            CheckIn.phone == phone,
            CheckIn.mode == "in",
        )
        .order_by(CheckIn.checked_in_at.desc())
        .first()
    )
    if existing:
        msg = "您已于 {} 签到，请勿重复签到".format(
            existing.checked_in_at.strftime("%Y-%m-%d %H:%M:%S") if existing.checked_in_at else "-")
        if _wants_json():
            return jsonify({"ok": False, "message": msg, "duplicate": True})
        ctx = _context(activity, mode)
        ctx.update({"message": msg, "ok": False})
        return render_template("scan.html", **ctx)

    db.session.add(
        CheckIn(
            activity_id=activity.id,
            name=name,
            phone=phone,
            campus=campus,
            code_used=site_code,
            mode="in",
            source="scan",
            checked_in_at=now,
        )
    )
    db.session.commit()
    msg = "签到成功！{} {}".format(name, campus)
    if _wants_json():
        return jsonify({"ok": True, "message": msg})
    ctx = _context(activity, mode)
    ctx.update({"message": msg, "ok": True})
    return render_template("scan.html", **ctx)
