"""Accounts: scrypt password hashes, signed session cookie carrying user id + per-user session
version (bump = log that user out everywhere), 30-day sliding sessions. Login attempts are
throttled per client IP (last X-Forwarded-For hop, which nginx overwrites)."""
import hashlib
import hmac
import secrets
import threading
import time

from fastapi import Request, Response
from itsdangerous import BadSignature, TimestampSigner, URLSafeTimedSerializer

from . import config, db

COOKIE = "nakladiak_session"
SESSION_DAYS = 30
MAX_AGE = SESSION_DAYS * 86400
RENEW_AFTER = 86400            # renew a cookie older than a day → 30 days from the last visit
FAIL_LIMIT = 6
FAIL_WINDOW = 15 * 60

_signer: TimestampSigner | None = None
_serializer: URLSafeTimedSerializer | None = None
_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def _get_signer() -> TimestampSigner:
    global _signer
    if _signer is None:
        _signer = TimestampSigner(config.secret_key(), salt="nakladiak-session")
    return _signer


def serializer() -> URLSafeTimedSerializer:
    """For one-purpose tokens (set-password links)."""
    global _serializer
    if _serializer is None:
        _serializer = URLSafeTimedSerializer(config.secret_key(), salt="nakladiak-token")
    return _serializer


# --- passwords ---------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    except (ValueError, TypeError):
        return False
    # compare bytes, not str: compare_digest refuses non-ASCII text
    return hmac.compare_digest(digest, bytes.fromhex(digest_hex))


# --- throttling --------------------------------------------------------------

def client_ip(request: Request) -> str:
    """The port is reachable only through nginx, which OVERWRITES X-Forwarded-For with the real
    client address. So: last hop of the header when present, else the peer. Never the first hop —
    a client can prepend anything. uvicorn runs without --proxy-headers."""
    peer = request.client.host if request.client else "?"
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[-1].strip() or peer
    return peer


def throttled(ip: str) -> bool:
    with _lock:
        now = time.time()
        recent = [t for t in _failures.get(ip, []) if now - t < FAIL_WINDOW]
        _failures[ip] = recent
        if len(_failures) > 5000:  # never let the map grow unbounded, but keep active blocks
            for k in [k for k, v in _failures.items() if not v]:
                _failures.pop(k, None)
        return len(recent) >= FAIL_LIMIT


def record_failure(ip: str) -> None:
    with _lock:
        now = time.time()
        if len(_failures) > 5000:
            # drop every key whose newest failure is outside the window (not just the empty ones)
            for k in [k for k, v in _failures.items() if not v or now - v[-1] >= FAIL_WINDOW]:
                _failures.pop(k, None)
        _failures.setdefault(ip, []).append(now)


def clear_failures(ip: str) -> None:
    with _lock:
        _failures.pop(ip, None)


# --- sessions ----------------------------------------------------------------

def make_cookie(user: dict) -> str:
    return _get_signer().sign(f"{user['id']}:{user['session_version']}".encode()).decode()


def user_from_cookie(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE)
    if not raw:
        return None
    try:
        payload, ts = _get_signer().unsign(raw, max_age=MAX_AGE, return_timestamp=True)
        uid_s, ver_s = payload.decode().split(":")
        uid, ver = int(uid_s), int(ver_s)
    except (BadSignature, ValueError):
        return None
    user = db.row(db.q1("SELECT * FROM users WHERE id=?", (uid,)))
    if user is None or user["session_version"] != ver or not user["active"]:
        return None
    request.state.session_age = time.time() - ts.timestamp()
    return user


def set_cookie(resp: Response, user: dict) -> None:
    resp.set_cookie(COOKIE, make_cookie(user), max_age=MAX_AGE, httponly=True,
                    samesite="lax", secure=config.is_https(), path="/")


def check_login(username: str, password: str) -> dict | None:
    user = db.row(db.q1("SELECT * FROM users WHERE username=?", (username.strip().lower(),)))
    if user is None or not user["password_hash"] or not user["active"]:
        # burn comparable time so a missing user is not distinguishable by latency
        verify_password(password, "scrypt$00$00")
        return None
    return user if verify_password(password, user["password_hash"]) else None


def set_password(user_id: int, new_plain: str, logout_everywhere: bool = True) -> None:
    with db.tx():
        db.run("UPDATE users SET password_hash=?, must_change_password=0 WHERE id=?", (hash_password(new_plain), user_id))
        if logout_everywhere:
            db.run("UPDATE users SET session_version=session_version+1 WHERE id=?", (user_id,))


def bootstrap_users() -> None:
    """First start: create the admin from .env. Later starts never touch passwords."""
    if db.q1("SELECT 1 FROM users LIMIT 1"):
        return
    a = config.bootstrap_admin()
    if not a["username"] or len(a["password"]) < 8:
        raise RuntimeError("Prvý štart: v .env musí byť ADMIN_PASSWORD (aspoň 8 znakov).")
    with db.tx():
        db.run("INSERT INTO users(username,name,email,password_hash,is_admin,created_at) VALUES(?,?,?,?,1,?)",
               (a["username"], a["name"], a["email"], hash_password(a["password"]), db.now_iso()))
    print("[auth] bootstrap: created admin", a["username"], flush=True)


# --- set-password links (invite / forgot) --------------------------------------

def _fingerprint(password_hash: str) -> str:
    return hmac.new(config.secret_key(), password_hash.encode(), hashlib.sha256).hexdigest()[:16]


def password_token(user: dict, purpose: str) -> str:
    """One-time: bound to the current password hash, so setting a password kills every link."""
    return serializer().dumps({"u": user["id"], "k": purpose, "f": _fingerprint(user["password_hash"])},
                              salt="set-password")


def load_password_token(token: str) -> dict | None:
    """Returns the user when the token is valid (unexpired, unused, user active)."""
    from itsdangerous import SignatureExpired
    try:
        data = serializer().loads(token, salt="set-password", max_age=7 * 86400)
    except (BadSignature, SignatureExpired):
        return None
    purpose = data.get("k")
    if purpose == "reset":
        try:
            serializer().loads(token, salt="set-password", max_age=3600)
        except (BadSignature, SignatureExpired):
            return None
    user = db.row(db.q1("SELECT * FROM users WHERE id=?", (int(data.get("u", 0)),)))
    if not user or not user["active"] or data.get("f") != _fingerprint(user["password_hash"]):
        return None
    return user
