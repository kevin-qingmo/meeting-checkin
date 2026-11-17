"""应用工厂。"""
import gzip
import os

from flask import Flask, render_template, request
from flask_login import current_user

from .assets import inline_css, inline_js, logo_data_uri
from .config import Config, engine_options
from .extensions import db, login_manager

# 弱网优化：小于该体积的响应不压缩（gzip 头本身有开销）
GZIP_MIN_SIZE = 1024
GZIP_TYPES = (
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
    "image/svg+xml",
)


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

    # 弱网优化：静态资源（CSS/JS/图片）走浏览器长缓存，二次打开不再重新握手
    # 注意：Flask 默认配置里这个键已存在且值为 None，必须直接赋值，setdefault 不生效
    app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 60 * 60 * 24

    # 弱网优化：数据库连接可能被中间链路静默断开，pool_pre_ping 让它在下次使用前
    # 快速探活并重建，而不是卡到超时；同时定期回收老连接
    if uri and not uri.startswith("sqlite"):
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options(uri)

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
        return {
            "current_user": current_user,
            "app_name": "会议扫码签到系统",
            # 弱网优化：首屏 CSS / JS / 校徽内联进 HTML，减少并行握手次数
            "inline_css": inline_css,
            "inline_js": inline_js,
            "logo_data_uri": logo_data_uri,
        }

    @app.after_request
    def maybe_gzip(response):
        """弱网优化：HTML / JSON / CSS / JS 走 gzip，显著减少传输字节数。"""
        try:
            mimetype = (response.mimetype or "").lower()
            if (
                mimetype in GZIP_TYPES
                and "gzip" in (request.headers.get("Accept-Encoding") or "")
                and response.status_code == 200
                and not response.direct_passthrough
            ):
                data = response.get_data()
                if len(data) >= GZIP_MIN_SIZE:
                    body = gzip.compress(data, 6)
                    if len(body) < len(data):
                        response.set_data(body)
                        response.headers["Content-Encoding"] = "gzip"
                        response.headers["Content-Length"] = str(len(body))
                        # 追加而不是覆盖：原 Vary 可能已含 Cookie，覆盖会破坏缓存语义
                        vary = response.headers.get("Vary", "")
                        if "accept-encoding" not in vary.lower():
                            response.headers["Vary"] = (vary + ", Accept-Encoding").strip(", ")
        except Exception:  # 压缩失败绝不能影响正常响应
            pass
        return response

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
