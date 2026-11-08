import os
import sys
from datetime import timedelta
from urllib.parse import quote_plus
from dotenv import load_dotenv
from sqlalchemy.engine import make_url


def _runtime_dir():
    """Folder that holds this PC's data. Next to the .exe when installed, else the project folder."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(os.path.dirname(__file__))


BASE_DIR = _runtime_dir()
DATA_DIR = os.path.join(BASE_DIR, "data")
load_dotenv(os.path.join(BASE_DIR, ".env"))
IS_VERCEL = os.getenv("VERCEL") == "1"


def _db_uri():
    # DATABASE_URL supports managed MySQL/PostgreSQL providers and test SQLite.
    # SQLAlchemy needs an explicit driver for PostgreSQL.
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        if database_url.startswith("postgres://"):
            database_url = "postgresql+psycopg://" + database_url[len("postgres://"):]
        elif database_url.startswith("postgresql://"):
            database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]
        if os.getenv("VERCEL") == "1" and database_url.startswith("postgresql+psycopg://"):
            url = make_url(database_url)
            return url.set(query={**url.query, "sslmode": "require"}).render_as_string(hide_password=False)
        return database_url
    # With no database settings, the institute PC uses a file in data/.
    if os.getenv("DB_PASSWORD"):
        user = quote_plus(os.getenv("DB_USER", "root"))
        pwd = quote_plus(os.getenv("DB_PASSWORD", ""))
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "3306")
        name = os.getenv("DB_NAME", "typetrack")
        return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}?charset=utf8mb4"
    path = os.path.join(DATA_DIR, "typetrack.db").replace("\\", "/")
    return "sqlite:///" + path


def _engine_options(uri):
    opts = {"pool_pre_ping": True}
    if uri.startswith("sqlite"):
        opts["connect_args"] = {"check_same_thread": False}
    elif uri.startswith("postgresql+psycopg://"):
        opts.update({
            "connect_args": {"prepare_threshold": None},
            "pool_size": 1,
            "max_overflow": 0,
            "pool_recycle": 300,
        })
    else:
        opts["pool_recycle"] = 280
    return opts


_URI = _db_uri()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    INSTITUTE_NAME = os.getenv("INSTITUTE_NAME", "My Typing Institute")
    INSTITUTE_OWNER_NAME = os.getenv("INSTITUTE_OWNER_NAME") or None
    INSTITUTE_ADDRESS = os.getenv("INSTITUTE_ADDRESS") or None
    INSTITUTE_PHONE = os.getenv("INSTITUTE_PHONE") or None
    INSTITUTE_EMAIL = os.getenv("INSTITUTE_EMAIL") or None
    INSTITUTE_WEBSITE = os.getenv("INSTITUTE_WEBSITE") or None
    INSTITUTE_RECEIPT_NOTE = os.getenv("INSTITUTE_RECEIPT_NOTE") or None
    SQLALCHEMY_DATABASE_URI = _URI
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    IS_VERCEL = IS_VERCEL
    UPLOAD_STORAGE_BACKEND = "supabase" if IS_VERCEL else "local"
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_STORAGE_BUCKET = os.getenv("SUPABASE_STORAGE_BUCKET", "typetrack-uploads")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER") or (
        os.path.join(DATA_DIR, "uploads")
        if getattr(sys, "frozen", False)
        else os.path.join(BASE_DIR, "static", "uploads")
    )
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "0") == "1"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    OVERDUE_DAYS = 30          # a balance is "overdue" this many days after admission
    PER_PAGE = 15
