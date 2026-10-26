"""Nakladiak — všetky pravidelné náklady domácností na jednom mieste. FastAPI app + middleware."""
import json
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import auth, config, db, scheduler
from .routers import api, pages
from .services import alerts

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nakladiak")

PUBLIC_PREFIXES = ("/login", "/forgot", "/static/", "/healthz", "/p/", "/manifest.webmanifest", "/sw.js", "/favicon.ico")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    auth.bootstrap_users()
    config.secret_key()
    config.DOCS_DIR.mkdir(parents=True, exist_ok=True)
    if os.environ.get("NAKLADIAK_NO_SCHEDULER") != "1":
        scheduler.start()
    log.info("Nakladiak started, db=%s tz=%s url=%s", config.DB_PATH, config.TZ_NAME, config.app_url())
    yield
    scheduler.stop()


app = FastAPI(title="Nakladiak", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(pages.router)
app.include_router(api.router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz():
    try:
        db.q1("SELECT 1")
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": "db"}, status_code=503)
    if os.environ.get("NAKLADIAK_NO_SCHEDULER") != "1" and not scheduler.healthy():
        return JSONResponse({"ok": False, "error": "scheduler"}, status_code=503)
    return {"ok": True}


@app.get("/manifest.webmanifest")
def manifest():
    data = {
        "name": "Nakladiak – náklady domácností", "short_name": "Nakladiak", "start_url": "/", "scope": "/",
        "display": "standalone", "background_color": "#f5f3ee", "theme_color": "#f5f3ee", "lang": "sk",
        "icons": [
            {"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "/static/img/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    return Response(json.dumps(data, ensure_ascii=False), media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return Response(open(os.path.join(STATIC_DIR, "js", "sw.js"), "rb").read(),
                    media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico")
def favicon():
    return RedirectResponse("/static/img/favicon.svg")


@app.middleware("http")
async def auth_and_headers(request: Request, call_next):
    # Gate on scope["path"] — what the router dispatches on — never on the raw URL.
    path = request.scope.get("path", "/")
    request.state.user = auth.user_from_cookie(request)
    is_public = any(path == p.rstrip("/") or path.startswith(p) for p in PUBLIC_PREFIXES)
    if not is_public and path != "/" and request.state.user is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Nie si prihlásený."}, status_code=401)
        return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
    if path.startswith("/api/") and request.method in ("POST", "PUT", "DELETE", "PATCH"):
        # CSRF: cookie auth + custom header the browser only adds to same-origin fetch().
        if request.headers.get("x-requested-with") != "nakladiak":
            return JSONResponse({"detail": "Chýba hlavička X-Requested-With."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") not in (config.app_url(), f"{request.url.scheme}://{request.headers.get('host', '')}"):
            return JSONResponse({"detail": "Neplatný pôvod požiadavky."}, status_code=403)
    u = request.state.user
    if u and u.get("must_change_password") and path.startswith("/api/") and path not in ("/api/me", "/api/profile/password"):
        return JSONResponse({"detail": "Najprv si zmeň heslo."}, status_code=403)
    response = await call_next(request)
    if u and getattr(request.state, "session_age", 0) > auth.RENEW_AFTER:
        auth.set_cookie(response, u)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if "Content-Security-Policy" not in h:  # a route may set a stricter one (document files: sandbox)
        h["Content-Security-Policy"] = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                        "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
                                        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")
    if config.is_https():
        h["Strict-Transport-Security"] = "max-age=31536000"
    if path.startswith("/p/") or path == "/forgot":
        h["Referrer-Policy"] = "no-referrer"
        h["Cache-Control"] = "no-store"
    elif path.startswith("/api/") or path in ("/", "/login") or path.endswith((".js", ".css", ".html")):
        h["Cache-Control"] = "no-cache"
    elif path.startswith("/static/"):
        h["Cache-Control"] = "public, max-age=604800"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.scope.get("path", "").startswith("/api/") or "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 404:
        return Response("Stránka neexistuje.", status_code=404, media_type="text/plain; charset=utf-8")
    return Response(str(exc.detail), status_code=exc.status_code, media_type="text/plain; charset=utf-8")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse({"detail": "Neplatné parametre požiadavky."}, status_code=422)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    path = request.scope.get("path", "")
    log.exception("unhandled error on %s", path)
    try:
        conn = db.connect()
        if conn.in_transaction:
            conn.execute("ROLLBACK")
    except Exception:  # noqa: BLE001
        pass
    alerts.alert(f"500:{path}:{type(exc).__name__}", "chyba 500", f"{path}: {type(exc).__name__}")
    return JSONResponse({"detail": "Interná chyba servera."}, status_code=500)
