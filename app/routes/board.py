import io
import time

import qrcode
from flask import (Blueprint, Response, current_app, jsonify, render_template,
                   request)
from flask_login import login_required

from ..access import activity_status, live_payload
from ..codes import current_cycle, make_site_code, make_token
from ..extensions import db
from ..models import Activity

bp = Blueprint("board", __name__)


def _get_activity(activity_id):
    act = db.session.get(Activity, activity_id)
    if act is None:
        return None
    return act


def _qr_url(activity_id, cycle, mode):
    base = current_app.config["BASE_URL"]
    token = make_token(activity_id, cycle, mode)
    return "{}/scan/{}?t={}&c={}&m={}".format(base, activity_id, token, cycle, mode)


@bp.route("/board/<int:activity_id>")
@login_required
def screen(activity_id):
    act = _get_activity(activity_id)
    if act is None:
        return render_template("error.html", code=404, message="活动不存在"), 404
    cycle = current_cycle()
    return render_template(
        "board.html",
        activity=act,
        status=activity_status(act),
        live=live_payload(act),
        cycle=cycle,
        mode="in",
        site_code=make_site_code(activity_id, cycle, "in"),
        qr_url=_qr_url(activity_id, cycle, "in"),
    )


@bp.route("/qr/<int:activity_id>.png")
@login_required
def qr_png(activity_id):
    if _get_activity(activity_id) is None:
        return Response(status=404)
    try:
        cycle = int(request.args.get("cycle") or current_cycle())
    except (TypeError, ValueError):
        cycle = current_cycle()
    mode = request.args.get("mode", "in")
    if mode not in ("in", "out"):
        mode = "in"
    url = _qr_url(activity_id, cycle, mode)
    qr = qrcode.QRCode(version=None, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(
        buf.getvalue(),
        mimetype="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@bp.route("/api/board/<int:activity_id>/qr")
@login_required
def board_qr(activity_id):
    act = _get_activity(activity_id)
    if act is None:
        return jsonify({"error": "活动不存在"}), 404
    mode = request.args.get("mode", "in")
    if mode not in ("in", "out"):
        mode = "in"
    cycle = current_cycle()
    seconds = current_app.config.get("CYCLE_SECONDS", 20)
    elapsed = int(time.time() % seconds)
    return jsonify({
        "cycle": cycle,
        "site_code": make_site_code(activity_id, cycle, mode),
        "token": make_token(activity_id, cycle, mode),
        "qr_url": _qr_url(activity_id, cycle, mode),
        "qr_png": "/qr/{}.png?cycle={}&mode={}".format(activity_id, cycle, mode),
        "mode": mode,
        "refresh_in": seconds - elapsed,
        "cycle_seconds": seconds,
        "status": activity_status(act),
    })
