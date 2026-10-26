"""Security invariants — several encode bugs earlier projects actually shipped."""
import re
from pathlib import Path

from fastapi.testclient import TestClient

from app import auth, config, db, settings
from app.main import app

from conftest import H, PDF, login, make_place

ROOT = Path(__file__).resolve().parents[1]


def test_password_hash_is_scrypt_and_handles_diacritics():
    h = auth.hash_password("heslóčkové123")
    assert h.startswith("scrypt$") and auth.verify_password("heslóčkové123", h)
    assert not auth.verify_password("heslockove123", h) and not auth.verify_password("", "")


def test_session_cookie_flags_renewal_and_revocation(client):
    c = TestClient(app, headers=H, follow_redirects=False)
    r = c.post("/login", data={"username": "jano", "password": "testheslo123", "next": "/"})
    cookie = r.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower() and f"Max-Age={auth.MAX_AGE}" in cookie
    assert ("Secure" in cookie) == config.is_https()
    bad = TestClient(app, headers=H)
    bad.cookies.set(auth.COOKIE, "1:1.tampered.signature")
    assert bad.get("/api/me").status_code == 401
    # logout everywhere invalidates the old cookie
    old = TestClient(app, headers=H, cookies=c.cookies)
    assert old.get("/api/me").status_code == 200
    c.post("/api/profile/logout-all")
    assert old.get("/api/me").status_code == 401


def test_secrets_never_leave_the_server(jano):
    jano.put("/api/settings", json={"anthropic_api_key": "sk-ant-tajny", "imap_password": "imap-tajne", "zsd_password": "zsd-tajne",
                                    "twocaptcha_api_key": "cap-tajne", "smtp_password": "smtp-tajne"})
    for path in ("/api/settings", "/api/me", "/api/history", "/api/about", "/api/connectors/status", "/api/meta"):
        body = jano.get(path).text
        for s in ("sk-ant-tajny", "imap-tajne", "zsd-tajne", "cap-tajne", "smtp-tajne"):
            assert s not in body, (path, s)
    assert settings.get("anthropic_api_key") == "sk-ant-tajny"
    jano.put("/api/settings", json={"_clear": ["anthropic_api_key"]})
    assert settings.get("anthropic_api_key") == ""


def test_write_endpoints_require_the_csrf_header_and_same_origin(jano):
    raw = TestClient(app, cookies=jano.cookies)
    assert raw.post("/api/places", json={"name": "X", "kind": "byt"}).status_code == 403
    assert raw.put("/api/profile", json={"name": "X"}).status_code == 403
    r = raw.post("/api/places", json={"name": "X", "kind": "byt"}, headers={"X-Requested-With": "nakladiak", "Origin": "https://evil.example"})
    assert r.status_code == 403
    assert raw.get("/api/me").status_code == 200


def test_security_headers_and_csp(jano):
    h = jano.get("/api/me").headers
    csp = h["content-security-policy"]
    for d in ("default-src 'self'", "script-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "form-action 'self'"):
        assert d in csp
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert h["cache-control"] == "no-cache"
    anon = TestClient(app, follow_redirects=False)
    assert anon.get("/p/not-a-token").headers["cache-control"] == "no-store"


def test_unauthenticated_reach_is_limited_to_the_public_surface():
    anon = TestClient(app, follow_redirects=False)
    for path in ("/api/me", "/api/dashboard", "/api/settings", "/api/places", "/api/documents", "/api/history", "/api/documents/1/file"):
        assert anon.get(path).status_code == 401, path
    assert anon.get("/").status_code == 303 and anon.head("/").status_code == 303
    assert anon.get("/login").status_code == 200 and anon.head("/login").status_code == 200
    assert anon.get("/healthz").status_code == 200 and anon.head("/healthz").status_code == 200
    assert anon.get("/manifest.webmanifest").status_code == 200
    assert anon.get("/login?next=//evil.example").status_code == 200


def test_login_throttling_per_ip(client):
    c = TestClient(app, headers=H, follow_redirects=False)
    for _ in range(6):
        c.post("/login", data={"username": "jano", "password": "zle", "next": "/"}, headers={"X-Forwarded-For": "203.0.113.9"})
    r = c.post("/login", data={"username": "jano", "password": "testheslo123", "next": "/"}, headers={"X-Forwarded-For": "203.0.113.9"})
    assert r.status_code == 429
    r = c.post("/login", data={"username": "jano", "password": "testheslo123", "next": "/"}, headers={"X-Forwarded-For": "203.0.113.10"})
    assert r.status_code == 303
    auth.clear_failures("203.0.113.9")


def test_rate_limit_key_uses_the_last_xff_hop():
    from starlette.requests import Request

    def req(peer, xff):
        scope = {"type": "http", "headers": [(b"x-forwarded-for", xff.encode())] if xff else [],
                 "client": (peer, 1234), "method": "GET", "path": "/", "scheme": "http", "server": ("test", 80), "query_string": b""}
        return Request(scope)
    assert auth.client_ip(req("172.18.0.1", "9.9.9.9, 1.2.3.4")) == "1.2.3.4"
    assert auth.client_ip(req("203.0.113.7", "")) == "203.0.113.7"
    cmd = [l for l in (ROOT / "Dockerfile").read_text().splitlines() if l.startswith("CMD")][0]
    assert "--proxy-headers" not in cmd and "--forwarded-allow-ips" not in cmd


def test_non_admin_cannot_manage_users_or_settings(jano):
    r = jano.post("/api/users", json={"username": "lucia", "name": "Lucia", "mode": "password", "password": "lucia12345", "must_change_password": False})
    assert r.status_code == 200, r.text
    lucia = login(jano, "lucia", "lucia12345")
    assert lucia.get("/api/settings").status_code == 403
    assert lucia.post("/api/users", json={"username": "x", "mode": "password", "password": "12345678"}).status_code == 403
    assert lucia.get("/api/history").status_code == 403
    assert lucia.get("/api/me").status_code == 200
    # the last admin cannot be demoted
    me = jano.get("/api/me").json()["user"]
    assert jano.put(f"/api/users/{me['id']}", json={"is_admin": False}).status_code == 400
    # deactivation kills the session
    uid = r.json()["user"]["id"]
    jano.put(f"/api/users/{uid}", json={"active": False})
    assert lucia.get("/api/me").status_code == 401


def test_must_change_password_blocks_other_api(jano):
    r = jano.post("/api/users", json={"username": "peter", "mode": "password", "password": "peter12345", "must_change_password": True})
    peter = login(jano, "peter", "peter12345")
    assert peter.get("/api/dashboard").status_code == 403
    assert peter.post("/api/profile/password", json={"current": "peter12345", "new": "peter1234567"}).status_code == 200
    peter2 = login(jano, "peter", "peter1234567")
    assert peter2.get("/api/dashboard").status_code == 200


def test_invite_link_is_one_time(jano):
    r = jano.post("/api/users", json={"username": "eva", "name": "Eva", "email": "eva@example.com", "mode": "invite"})
    assert r.status_code == 200 and r.json()["mail_sent"] is False and "/p/" in r.json()["invite_url"]
    url = r.json()["invite_url"].replace("http://testserver", "")
    anon = TestClient(app, follow_redirects=False)
    assert anon.get(url).status_code == 200
    assert anon.post(url, data={"password": "evaheslo123", "password2": "evaheslo123"}).status_code == 303
    assert anon.get(url).status_code == 400  # used
    assert login(jano, "eva", "evaheslo123").get("/api/me").status_code == 200


def test_forgot_gives_the_same_answer_for_any_account():
    anon = TestClient(app)
    a = anon.post("/forgot", data={"who": "jano"}).text
    b = anon.post("/forgot", data={"who": "nikto"}).text
    assert a == b


def test_settings_reject_dangerous_values(jano):
    bad = [("smtp_port", "99999"), ("smtp_host", "a b"), ("ntfy_server", "file:///etc/passwd"), ("ntfy_server", "http://169.254.169.254/x"),
           ("ntfy_server", "https://10.0.0.1/"), ("zsd_time", "25:00"), ("claude_model", "../x"), ("imap_enabled", "yes"),
           ("statement_reminder_days", "-1"), ("smtp_from", "not-an-email")]
    for key, val in bad:
        assert jano.put("/api/settings", json={key: val}).status_code == 400, f"{key}={val!r}"
    good = [("smtp_port", "465"), ("ntfy_server", "https://ntfy.sh"), ("zsd_time", "14:35"), ("claude_model", "claude-sonnet-5-5"), ("statement_reminder_days", "45")]
    for key, val in good:
        assert jano.put("/api/settings", json={key: val}).status_code == 200, f"{key}={val!r}"


def test_control_characters_are_stripped(jano):
    CR, LF, RLO = chr(13), chr(10), chr(0x202e)
    r = jano.put("/api/profile", json={"name": "Jano" + CR + LF + "Bcc: evil@example.com"})
    assert r.status_code == 200 and LF not in r.json()["name"]
    p = make_place(jano, "Byt" + RLO + "x")
    assert RLO not in p["name"]


def test_document_file_path_cannot_escape(jano):
    from app.services import documents
    doc = {"path": "../../etc/passwd", "mime": "application/pdf"}
    try:
        documents.file_path(doc)
        assert False, "traversal allowed"
    except documents.DocError:
        pass


def test_service_worker_never_caches_api_or_html():
    sw = (ROOT / "app/static/js/sw.js").read_text()
    body = sw[sw.index("addEventListener('fetch'"):]
    assert body.count("c.put(") == 1 and "startsWith('/static/')" in body and "ignoreSearch" not in body
    assert body.index("fetch(e.request)") < body.index("c.match(e.request)")


def test_spa_has_a_single_html_sink():
    js_path = ROOT / "app/static/js/app.js"
    if not js_path.is_file():
        return
    js = js_path.read_text()
    for m in re.finditer(r"html:\s*([A-Za-z_$][\w.$\[\]'\"]*)", js):
        assert m.group(1).startswith("ICONS["), m.group(0)
    assert len(re.findall(r"\.innerHTML\s*=", js)) == 1
    assert "insertAdjacentHTML" not in js and "document.write" not in js


def test_upload_size_is_checked_before_reading(jano):
    r = jano.post("/api/documents", files={"file": ("x.pdf", PDF, "application/pdf")},
                  headers={"Content-Length": str(config.MAX_UPLOAD_BYTES + 100000)})
    assert r.status_code in (400, 413)
