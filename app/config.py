import os


def engine_options(uri):
    """数据库连接池参数。

    弱网（跨境丢包）环境下连接容易被中间链路静默断开，
    pool_pre_ping 让连接在下次使用前先探活、必要时重建，
    pool_recycle 定期回收老连接，避免卡到超时。
    """
    if not uri or uri.startswith("sqlite"):
        return {}
    return {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": 5,
        "max_overflow": 5,
        "pool_timeout": 30,
        "connect_args": {"connect_timeout": 15},
    }


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///checkin.db")
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASE_URL = os.environ.get("BASE_URL", "http://localhost:5000").rstrip("/")
    CYCLE_SECONDS = int(os.environ.get("CYCLE_SECONDS", "20"))
    # 签到码容忍窗：弱网下大屏刷新滞后时，允许使用略旧的二维码（单位：周期）
    CYCLE_GRACE = int(os.environ.get("CYCLE_GRACE", "2"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024
    JSON_AS_ASCII = False


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SECRET_KEY = "test-secret"
    WTF_CSRF_ENABLED = False
