from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from ..extensions import db
from ..models import User

bp = Blueprint("auth", __name__)


def _safe_next(target):
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return None


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin.activities"))
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = db.session.query(User).filter(User.username == username).first()
        if user and user.active and user.check_password(password):
            login_user(user)
            nxt = _safe_next(request.args.get("next"))
            return redirect(nxt or url_for("admin.activities"))
        flash("用户名或密码错误", "error")
    return render_template("login.html", next=request.args.get("next") or "")


@bp.route("/logout")
def logout():
    logout_user()
    flash("已退出登录", "success")
    return redirect(url_for("auth.login"))
