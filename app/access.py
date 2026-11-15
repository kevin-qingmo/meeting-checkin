"""公共访问控制与业务辅助。"""
from datetime import datetime

from flask import abort
from flask_login import current_user

from .extensions import db
from .models import Activity, CheckIn, Roster, Setting


def dict_campuses():
    return Setting.list_of("campuses")


def dict_stages():
    return Setting.list_of("stages")


def dict_subjects():
    return Setting.list_of("subjects")


def name_map(items):
    return {i["id"]: i["name"] for i in items}


def activity_status(activity, now=None):
    now = now or datetime.now()
    if now < activity.start_at:
        return "not_started"
    if now > activity.end_at:
        return "ended"
    return "ongoing"


def can_manage(user, activity):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if user.is_super:
        return True
    return activity.owner_id == user.id


def get_managed_activity(activity_id):
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        abort(404)
    if not can_manage(current_user, activity):
        abort(403)
    return activity


def activity_stats(activity):
    records = activity.checkins
    checked_in = [r for r in records if r.mode == "in"]
    checked_out = [r for r in checked_in if r.checked_out_at is not None]
    expected = Roster.query.filter_by(activity_id=activity.id).count()
    signed_names = {(r.name or "").strip() for r in checked_in}
    absent = []
    if expected:
        signed_phones = {(r.phone or "").strip() for r in checked_in if (r.phone or "").strip()}
        for row in Roster.query.filter_by(activity_id=activity.id).all():
            if (row.phone or "").strip() and (row.phone or "").strip() in signed_phones:
                continue
            if (row.name or "").strip() in signed_names:
                continue
            absent.append(row)
    return {
        "checked_in": len(checked_in),
        "checked_out": len(checked_out),
        "expected": expected,
        "absent": absent,
        "records": checked_in,
    }


def live_payload(activity):
    stats = activity_stats(activity)
    recent = sorted(
        stats["records"],
        key=lambda r: r.checked_in_at or datetime.min,
        reverse=True,
    )[:20]
    return {
        "checked_in": stats["checked_in"],
        "checked_out": stats["checked_out"],
        "expected": stats["expected"],
        "status": activity_status(activity),
        "need_checkout": activity.need_checkout,
        "absent": [{"name": r.name, "campus": r.campus, "phone": r.phone or ""} for r in stats["absent"]],
        "records": [
            {
                "id": r.id,
                "name": r.name,
                "campus": r.campus,
                "phone": r.phone or "",
                "source": r.source,
                "checked_in_at": r.checked_in_at.strftime("%Y-%m-%d %H:%M:%S") if r.checked_in_at else "",
                "checked_out_at": r.checked_out_at.strftime("%Y-%m-%d %H:%M:%S") if r.checked_out_at else "",
            }
            for r in recent
        ],
    }
