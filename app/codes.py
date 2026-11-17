import hashlib
import hmac
import time

from flask import current_app


def current_cycle(now=None):
    """当前所处签到周期序号（每 CYCLE_SECONDS 秒一个周期）。"""
    ts = now if now is not None else time.time()
    seconds = current_app.config.get("CYCLE_SECONDS", 20) if current_app else 20
    return int(ts // seconds)


def _digest(activity_id, cycle, mode="in"):
    key = (current_app.config["SECRET_KEY"] if current_app else "dev-secret-change-me").encode("utf-8")
    msg = "{}:{}:{}".format(activity_id, cycle, mode or "in").encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def make_token(activity_id, cycle, mode="in"):
    """签到码（进二维码 URL 的 token）。mode 参与运算，切换签到/签离即换新码。"""
    return _digest(activity_id, cycle, mode)[:16]


def make_site_code(activity_id, cycle, mode="in"):
    """现场码：4 位数字，每个签到码对应一个。"""
    return str(int(_digest(activity_id, cycle, mode)[:8], 16) % 10000).zfill(4)


def verify(activity_id, token, code, cycle, mode="in", now=None):
    """校验扫码 token + 现场码。

    容忍窗：接受当前周期往前 grace 个周期（默认 2，即约 60 秒）。
    跨境弱网时大屏刷新本身可能滞后一两个周期，若只容忍 1 个周期，
    老师扫的是过期码会直接失败，因此容忍窗做成可配置（环境变量 CYCLE_GRACE）。

    返回 (是否通过, 失败原因)
    """
    if not token or not code or cycle in (None, ""):
        return False, "签到码无效，请重新扫码"
    try:
        cycle = int(cycle)
    except (TypeError, ValueError):
        return False, "签到码无效，请重新扫码"
    cur = current_cycle(now)
    grace = current_app.config.get("CYCLE_GRACE", 2) if current_app else 2
    try:
        grace = max(0, int(grace))
    except (TypeError, ValueError):
        grace = 2
    if cycle not in {cur - i for i in range(grace + 1)}:
        return False, "签到码已刷新，请使用大屏上最新的现场码"
    if not hmac.compare_digest(str(token), make_token(activity_id, cycle, mode)):
        return False, "签到码无效，请重新扫码"
    if not hmac.compare_digest(str(code).strip(), make_site_code(activity_id, cycle, mode)):
        return False, "现场码不正确"
    return True, ""
