from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ..access import get_managed_activity, live_payload
from ..extensions import db
from ..lottery import recent_rounds
from ..models import Activity, CheckIn

bp = Blueprint("api", __name__)


@bp.route("/api/health")
def health():
    return jsonify({"ok": True, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


@bp.route("/api/activity/<int:activity_id>/live")
@login_required
def live(activity_id):
    act = get_managed_activity(activity_id)
    return jsonify(live_payload(act))


@bp.route("/api/activity/<int:activity_id>/manual", methods=["POST"])
@login_required
def manual_checkin(activity_id):
    act = get_managed_activity(activity_id)
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    campus = (request.form.get("campus") or "").strip()
    if not name:
        return jsonify({"ok": False, "message": "请填写姓名"}), 400
    if not campus:
        return jsonify({"ok": False, "message": "请选择校区"}), 400

    checked_in_at = _parse_dt(request.form.get("checked_in_at")) or datetime.now()
    checked_out_at = _parse_dt(request.form.get("checked_out_at"))

    record = CheckIn(
        activity_id=act.id,
        name=name,
        phone=phone,
        campus=campus,
        code_used="补录",
        mode="in",
        source="manual",
        checked_in_at=checked_in_at,
        checked_out_at=checked_out_at,
        operator_id=current_user.id,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"ok": True, "message": "已补录 {} 的签到记录".format(name), "id": record.id})


@bp.route("/api/checkin/<int:checkin_id>/delete", methods=["POST"])
@login_required
def delete_checkin(checkin_id):
    record = db.session.get(CheckIn, checkin_id)
    if record is None:
        return jsonify({"ok": False, "message": "记录不存在"}), 404
    get_managed_activity(record.activity_id)
    db.session.delete(record)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除该条记录"})


def _parse_dt(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _public_round(round_data):
    """公开视图：抹掉中奖人手机号，只保留姓名与校区；脏数据元素直接跳过。"""
    if not round_data:
        return round_data
    public = dict(round_data)
    public["winners"] = [
        {"name": w.get("name", ""), "campus": w.get("campus", "")}
        for w in (round_data.get("winners") or [])
        if isinstance(w, dict)
    ]
    return public


@bp.route("/api/activity/<int:activity_id>/lottery")
def activity_lottery(activity_id):
    """抽签记录（公开只读，供大屏投屏使用；中奖人手机号不外泄）。"""
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        return jsonify({"ok": False, "message": "活动不存在"}), 404
    rounds = [_public_round(r) for r in recent_rounds(activity, 5)]
    return jsonify({"ok": True, "rounds": rounds, "latest": rounds[0] if rounds else None})
