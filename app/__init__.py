"""应用工厂。"""
import os

from flask import Flask, render_template
from flask_login import current_user

from .config import Config
from .extensions import db, login_manager


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.json.ensure_ascii = False

    if test_config:
        app.config.update(test_config)

    # 生产安全护栏：SECRET_KEY 决定签到码能否被伪造，连接真实数据库时不允许用默认值
    default_secret = "dev-secret-change-me"
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if (uri and not uri.startswith("sqlite")
            and app.config.get("SECRET_KEY") == default_secret):
        raise RuntimeError(
            "SECRET_KEY 仍是默认值，签到码可被伪造，已拒绝启动。"
            "请在部署平台设置环境变量 SECRET_KEY 为任意随机字符串后重新部署。"
        )

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from .routes.auth import bp as auth_bp
    from .routes.admin import bp as admin_bp
    from .routes.board import bp as board_bp
    from .routes.scan import bp as scan_bp
    from .routes.api import bp as api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(board_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(api_bp)

    @login_manager.user_loader
    def load_user(user_id):
        from .models import User
        try:
            return db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None

    @app.context_processor
    def inject_globals():
        return {"current_user": current_user, "app_name": "会议扫码签到系统"}

    @app.template_filter("dt")
    def format_dt(value, with_seconds=True):
        if not value:
            return ""
        return value.strftime("%Y-%m-%d %H:%M:%S" if with_seconds else "%Y-%m-%d %H:%M")

    @app.errorhandler(403)
    def err_403(e):
        return render_template("error.html", code=403, message="没有权限访问该页面"), 403

    @app.errorhandler(404)
    def err_404(e):
        return render_template("error.html", code=404, message="页面不存在"), 404

    with app.app_context():
        db.create_all()

    return app
