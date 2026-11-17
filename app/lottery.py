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


def winner_items(winners):
    """从中奖人列表中取出合法的（dict）条目，跳过脏数据。

    winners_json 是库里的原始文本，可能被写成合法 JSON list 但元素并非 dict
    （如 '["oops"]'）。所有按元素取字段的地方都必须先过这一层，
    否则脏数据会让接口抛 AttributeError。
    """
    return [w for w in (winners or []) if isinstance(w, dict)]


def past_winner_keys(activity):
    """该活动所有历史轮次中奖人的去重键集合。"""
    keys = set()
    for row in LotteryRound.query.filter_by(activity_id=activity.id).all():
        for w in winner_items(row.winners):
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


def round_seq_map(activity_id):
    """该活动内各轮次的「活动内序号」映射：{轮次 id: 1..n}。

    轮次的全局 id 跨活动不连续，复盘时「第几轮」必须是活动内序号，
    后台与 Excel 导出都以此为唯一口径。
    """
    rows = (LotteryRound.query.filter_by(activity_id=activity_id)
            .order_by(LotteryRound.id).all())
    return {row.id: idx for idx, row in enumerate(rows, 1)}


def serialize_round(round_row, operator_name="", seq=None):
    """序列化一轮抽签记录。seq 为活动内序号（不给时按活动内 id 升序现算）。"""
    if seq is None:
        seq = round_seq_map(round_row.activity_id).get(round_row.id)
    return {
        "id": round_row.id,
        "seq": seq,
        "draw_count": round_row.draw_count,
        "winners": round_row.winners,
        "excluded": bool(round_row.excluded),
        "created_at": round_row.created_at.strftime("%Y-%m-%d %H:%M:%S") if round_row.created_at else "",
        "operator": operator_name or "",
    }


def _serialize_rows(rows):
    """批量序列化（同一活动的轮次），活动内序号只算一次。"""
    if not rows:
        return []
    seqs = round_seq_map(rows[0].activity_id)
    out = []
    for row in rows:
        name = row.operator.display_name if row.operator else ""
        out.append(serialize_round(row, name, seqs.get(row.id)))
    return out


def recent_rounds(activity, limit=5):
    """最近若干轮（默认 5），按时间倒序；活动内序号仍按全部轮次计算。"""
    rows = (LotteryRound.query.filter_by(activity_id=activity.id)
            .order_by(LotteryRound.id.desc()).limit(limit).all())
    return _serialize_rows(rows)


def all_rounds(activity):
    """该活动的全部轮次（后台历史用），按时间倒序。"""
    rows = (LotteryRound.query.filter_by(activity_id=activity.id)
            .order_by(LotteryRound.id.desc()).all())
    return _serialize_rows(rows)
