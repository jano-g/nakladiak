"""HTML pages: app shell, login/logout, set-password links (invite + forgot)."""
import logging
import threading
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import auth, config, db, util
from ..services import mailer
from ..templating import render

log = logging.getLogger(__name__)
router = APIRouter()
_forgot_lock = threading.Lock()
_forgot_ip: dict[str, list[float]] = {}
_forgot_user: dict[int, float] = {}


def _safe_next(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt else "/"


@router.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
def index(request: Request):
    if getattr(request.state, "user", None) is None:
        return RedirectResponse("/login", status_code=303)
    return render(request, "index.html")


@router.api_route("/login", methods=["GET", "HEAD"], response_class=HTMLResponse)
def login_form(request: Request, next: str = "/", error: str = ""):
    if getattr(request.state, "user", None) is not None:
        return RedirectResponse(_safe_next(next), status_code=303)
    return render(request, "login.html", {"error": LOGIN_ERRORS.get(error, ""), "next": _safe_next(next), "smtp": mailer.is_configured()})


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""), next: str = Form("/")):
    ip = auth.client_ip(request)
    if auth.throttled(ip):
        return render(request, "login.html", {"error": "Priveľa pokusov. Skús to o 15 minút.", "next": _safe_next(next)},
                      status_code=429)
    user = auth.check_login(username, password)
    if user is None:
        auth.record_failure(ip)
        db.log_history(None, "login_failed", {}, ip)  # never the typed name: people paste passwords into it
        return render(request, "login.html", {"error": "Nesprávne meno alebo heslo.", "next": _safe_next(next),
                                              "username": username[:40]}, status_code=401)
    auth.clear_failures(ip)
    db.run("UPDATE users SET last_login_at=? WHERE id=?", (db.now_iso(), user["id"]))
    db.log_history(user["id"], "login", {}, ip)
    resp = RedirectResponse(_safe_next(next), status_code=303)
    auth.set_cookie(resp, user)
    return resp


@router.post("/logout")
def logout(request: Request):
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE, path="/")
    return resp


# --- set-password links --------------------------------------------------------

@router.get("/p/{token}", response_class=HTMLResponse)
def set_password_form(request: Request, token: str):
    user = auth.load_password_token(token)
    if not user:
        return render(request, "password.html", {"invalid": True}, status_code=400)
    return render(request, "password.html", {"token": token, "name": user["name"]})


@router.post("/p/{token}", response_class=HTMLResponse)
def set_password_do(request: Request, token: str, password: str = Form(""), password2: str = Form("")):
    user = auth.load_password_token(token)
    if not user:
        return render(request, "password.html", {"invalid": True}, status_code=400)
    if len(password) < 8:
        return render(request, "password.html", {"token": token, "name": user["name"], "error": "Heslo musí mať aspoň 8 znakov."}, status_code=400)
    if password != password2:
        return render(request, "password.html", {"token": token, "name": user["name"], "error": "Heslá sa nezhodujú."}, status_code=400)
    auth.set_password(user["id"], password)
    db.log_history(user["id"], "password_set_via_link", {}, auth.client_ip(request))
    fresh = db.row(db.q1("SELECT * FROM users WHERE id=?", (user["id"],)))
    resp = RedirectResponse("/", status_code=303)
    auth.set_cookie(resp, fresh)
    return resp


LOGIN_ERRORS = {"throttled": "Priveľa pokusov. Skús to o 15 minút.", "bad": "Nesprávne meno alebo heslo."}


def _forgot_allowed(ip: str, uid: int | None) -> bool:
    with _forgot_lock:
        now = time.time()
        if len(_forgot_ip) > 5000:
            for k in [k for k, v in _forgot_ip.items() if not v or now - v[-1] >= 900]:
                _forgot_ip.pop(k, None)
        recent = [t for t in _forgot_ip.get(ip, []) if now - t < 900]
        _forgot_ip[ip] = recent + [now]
        if len(recent) >= 5:
            return False
        if uid is not None:
            if now - _forgot_user.get(uid, 0) < 300:
                return False
            _forgot_user[uid] = now
        return True


@router.api_route("/forgot", methods=["GET", "HEAD"], response_class=HTMLResponse)
def forgot_form(request: Request):
    return render(request, "forgot.html", {"smtp": mailer.is_configured()})


@router.post("/forgot", response_class=HTMLResponse)
def forgot_do(request: Request, who: str = Form("")):
    ip = auth.client_ip(request)
    who = util.clean_text(who, 120).lower()
    user = db.row(db.q1("SELECT * FROM users WHERE active=1 AND (username=? OR (email<>'' AND lower(email)=?))", (who, who)))
    if _forgot_allowed(ip, user["id"] if user else None) and user and user["email"] and mailer.is_configured():
        url = f"{config.app_url()}/p/{auth.password_token(user, 'reset')}"
        host = config.app_url().split("//", 1)[-1]
        body = (f"<p>Ahoj {mailer.esc(user['name'])},</p><p>niekto (asi ty) požiadal o nové heslo do appky na {mailer.esc(host)}. "
                f"Odkaz platí hodinu.</p><p>Ak si o to nežiadal(a), mail ignoruj — heslo sa nezmenilo.</p>")
        db.log_history(user["id"], "password_reset_requested", {}, ip)

        def work(to=user["email"]):
            # in a thread: the response time must not reveal whether the account exists
            try:
                mailer.send(to, f"Nové heslo do {host}", mailer.wrap(body, [("Nastaviť nové heslo", url)]),
                            f"Nové heslo do {host}: {url}\nOdkaz platí hodinu. Ak si o to nežiadal(a), mail ignoruj.")
            except Exception as exc:  # noqa: BLE001
                log.warning("reset mail failed: %s", exc)
                db.log_history(None, "mail_failed", {"to": to, "subject": "reset", "error": str(exc)[:200]})
            finally:
                db.close()
        threading.Thread(target=work, daemon=True).start()
    return render(request, "forgot.html", {"smtp": mailer.is_configured(), "sent": True})
