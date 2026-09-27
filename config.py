import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)


class Config:
    SECRET_KEY = (
        os.environ.get("SECRET_KEY")
    )

    SQLALCHEMY_DATABASE_URI = (
        database_url or f"sqlite:///{os.path.join(basedir, 'freks.db')}"
    )

    # Caps how many DB connections each Gunicorn worker can open. Supabase's
    # pooler enforces a hard connection ceiling — without this, SQLAlchemy's
    # defaults (pool_size=5, max_overflow=10 = 15 per worker) multiply across
    # every worker process and blow past that ceiling under real load.
    # 4 workers * (2 + 1) = 12 connections, safely under a 15-connection cap.
    # prepare_threshold=None is required when DATABASE_URL points at the
    # transaction-mode pooler (port 6543), which doesn't support prepared
    # statements. Harmless to leave set if using the session-mode pooler.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 1,
        "max_overflow": 0,
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "connect_args": {"prepare_threshold": None},
    }

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "images", "products")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    REMEMBER_COOKIE_DURATION = timedelta(days=30)
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)  # keep the session cookie's lifetime matched to REMEMBER_COOKIE_DURATION, so the custom auth token in it survives exactly as long as the remember-me cookie does
    WTF_CSRF_ENABLED = True

    EMAIL_VERIFY_MAX_AGE_SECONDS = 3600  # 1 hour
    PASSWORD_RESET_MAX_AGE_SECONDS = 1800  # 30 minutes

    # Cookie hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}