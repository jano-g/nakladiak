"""Process-level configuration: environment variables, paths, time zone, signing secret.

`.env` is the base. Keys listed in `settings.OVERRIDABLE` can be changed in the app
(Nastavenia); a non-empty DB value wins over the environment.
"""
import os
import secrets
from pathlib import Path
from zoneinfo import ZoneInfo

APP_NAME = "Nakladiak"
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
DB_PATH = Path(os.environ.get("NAKLADIAK_DB", str(DATA_DIR / "nakladiak.db")))
DOCS_DIR = Path(os.environ.get("NAKLADIAK_DOCS", str(DATA_DIR / "docs")))
TZ_NAME = os.environ.get("APP_TZ", "Europe/Bratislava")
TZ = ZoneInfo(TZ_NAME)
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
BUILT_AT_PATH = Path("/srv/BUILT_AT")


def app_url() -> str:
    return os.environ.get("APP_URL", "http://localhost:8180").rstrip("/")


def is_https() -> bool:
    return app_url().startswith("https://")


_secret: bytes | None = None


def secret_key() -> bytes:
    """Cookie/token signing key. SECRET_KEY from env (>= 32 chars), else generated once into
    data/secret.key (O_EXCL so two concurrent starts never both write). Persisted so a restart
    or deploy never logs anyone out."""
    global _secret
    if _secret is not None:
        return _secret
    env = os.environ.get("SECRET_KEY", "").strip()
    if env:
        if len(env) >= 32:
            _secret = env.encode()
            return _secret
        print("[config] SECRET_KEY je kratší ako 32 znakov — ignorujem, použijem /data/secret.key", flush=True)
    path = DATA_DIR / "secret.key"
    if path.is_file():
        data = path.read_bytes().strip()
        if len(data) >= 32:
            _secret = data
            return _secret
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fresh = secrets.token_urlsafe(48).encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(fresh)
        _secret = fresh
    except FileExistsError:
        _secret = path.read_bytes().strip()
    return _secret


def bootstrap_admin() -> dict:
    """The admin account from .env, used only on first start (empty users table)."""
    return {
        "username": (os.environ.get("ADMIN_USERNAME", "") or "jano").strip().lower(),
        "name": os.environ.get("ADMIN_NAME", "").strip() or (os.environ.get("ADMIN_USERNAME", "") or "jano").strip().capitalize(),
        "email": os.environ.get("ADMIN_EMAIL", "").strip(),
        "password": os.environ.get("ADMIN_PASSWORD", ""),
    }


def built_at() -> str:
    try:
        return BUILT_AT_PATH.read_text().strip()
    except OSError:
        return ""
