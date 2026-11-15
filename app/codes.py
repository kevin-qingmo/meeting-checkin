import hashlib
import hmac
import time

from flask import current_app


def current_cycle(now=None):
    """当前所处签到周期序号（每 CYCLE_SECONDS 秒一个周期）。"""
    ts = now if now is not None else time.time()
    seconds = current_app.config.get("CYCLE_SECONDS", 20) if current_app else 20
    return int(ts // seconds)


def _digest(activity_id, cycle):
    key = (current_app.config["SECRET_KEY"] if current_app else "dev-secret-change-me").encode("utf-8")
    msg = "{}:{}".format(activity_id, cycle).encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def make_token(activity_id, cycle):
    """签到码（进二维码 URL 的 token）。"""
    return _digest(activity_id, cycle)[:16]


def make_site_code(activity_id, cycle):
    """现场码：4 位数字，每个签到码对应一个。"""
    return str(int(_digest(activity_id, cycle)[:8], 16) % 10000).zfill(4)


def verify(activity_id, token, code, cycle, now=None):
    """校验扫码 token + 现场码。接受当前与上一周期（40 秒容忍窗）。

    返回 (是否通过, 失败原因)
    """
    if not token or not code or cycle in (None, ""):
        return False, "签到码无效，请重新扫码"
    try:
        cycle = int(cycle)
    except (TypeError, ValueError):
        return False, "签到码无效，请重新扫码"
    cur = current_cycle(now)
    if cycle not in (cur, cur - 1):
        return False, "签到码已刷新，请使用大屏上最新的现场码"
    if not hmac.compare_digest(str(token), make_token(activity_id, cycle)):
        return False, "签到码无效，请重新扫码"
    if not hmac.compare_digest(str(code).strip(), make_site_code(activity_id, cycle)):
        return False, "现场码不正确"
    return True, ""
