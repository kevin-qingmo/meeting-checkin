"""随机抽签领域逻辑：候选池、历史中奖人、随机抽取与轮次留痕。"""
import json
import secrets

from .extensions import db
from .models import CheckIn, LotteryRound


def person_key(name, campus, phone):
    """去重键：优先手机号，其次姓名+校区。"""
    phone = (phone or "").strip()
    if phone:
        return "p:" + phone
    return "n:" + (name or "").strip() + "|" + (campus or "").strip()


def candidate_pool(activity):
    """候选池 = 该活动已签到人员（扫码与补录都算），按去重键去重。"""
    rows = CheckIn.query.filter_by(activity_id=activity.id).all()
    pool, seen = [], set()
    for row in rows:
        if row.checked_in_at is None:
            continue
        key = person_key(row.name, row.campus, row.phone)
        if key in seen:
            continue
        seen.add(key)
        pool.append(row)
    return pool


def past_winner_keys(activity):
    """该活动所有历史轮次中奖人的去重键集合。"""
    keys = set()
    for row in LotteryRound.query.filter_by(activity_id=activity.id).all():
        for w in row.winners:
            keys.add(person_key(w.get("name"), w.get("campus"), w.get("phone")))
    return keys


def draw(activity, count, exclude_winners=True):
    """随机抽取。返回 (winners, available_count)。"""
    pool = candidate_pool(activity)
    blocked = past_winner_keys(activity) if exclude_winners else set()
    available = [r for r in pool
                 if person_key(r.name, r.campus, r.phone) not in blocked]
    try:
        k = int(count)
    except (TypeError, ValueError):
        k = 1
    k = max(1, k)
    picked = secrets.SystemRandom().sample(available, min(k, len(available)))
    winners = [{"name": r.name, "campus": r.campus or "", "phone": r.phone or ""} for r in picked]
    return winners, len(available)


def save_round(activity, winners, draw_count, excluded, operator_id):
    """写入一轮抽签记录。候选池为空时不落库，返回 None。"""
    if not winners:
        return None
    row = LotteryRound(
        activity_id=activity.id,
        draw_count=draw_count,
        winners_json=json.dumps(winners, ensure_ascii=False),
        excluded=bool(excluded),
        operator_id=operator_id,
    )
    db.session.add(row)
    db.session.commit()
    return row


def serialize_round(round_row, operator_name=""):
    return {
        "id": round_row.id,
        "draw_count": round_row.draw_count,
        "winners": round_row.winners,
        "excluded": bool(round_row.excluded),
        "created_at": round_row.created_at.strftime("%Y-%m-%d %H:%M:%S") if round_row.created_at else "",
        "operator": operator_name or "",
    }


def recent_rounds(activity, limit=5):
    rows = (LotteryRound.query.filter_by(activity_id=activity.id)
            .order_by(LotteryRound.id.desc()).limit(limit).all())
    out = []
    for row in rows:
        name = row.operator.display_name if row.operator else ""
        out.append(serialize_round(row, name))
    return out
