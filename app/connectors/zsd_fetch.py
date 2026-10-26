"""Subprocess: log in to ZSD diportal with headless Chromium, read interval data for the
requested delivery points, print ONE JSON line to stdout. Config comes as JSON on stdin:

  {"user", "password", "business_partner_id", "twocaptcha_api_key", "days", "explore",
   "services": [{"service_id", "delivery_point_id", "generation_ref"}]}

Output: {"services": [{"service_id", "consumption": {date: [kwh, intervals]}, "generation": {...}}],
         "delivery_points": [...], "errors": [...]}

Everything else (progress, debugging) goes to stderr. Ported from spotreba_bela/fetch.py."""
import datetime
import json
import re
import sys
import time
import urllib.parse
import urllib.request

PORTAL_URL = "https://www.diportal.sk/portal/#/verejne/prihlasenie"
API_URL = "https://www.diportal.sk/portal/api/interval-data/getProfileData"
DELIVERY_POINTS_URL = "https://www.diportal.sk/portal/api/delivery-points-list/loadDeliveryPoints"
RECAPTCHA_SITE_KEY = "6LfdaLUZAAAAAHCVziF1iDFvmCxAjlIP1xF6pjHg"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
MIN_COMPLETE_INTERVALS = 88   # a day has 96 quarter hours (92/100 on DST changes)
MAX_DAY_CALLS = 60


def log(msg: str) -> None:
    print(f"[zsd] {msg}", file=sys.stderr, flush=True)


# --- 2captcha ------------------------------------------------------------------

def solve_recaptcha(api_key: str, page_url: str) -> str:
    submit_url = "https://2captcha.com/in.php?" + urllib.parse.urlencode({
        "key": api_key, "method": "userrecaptcha", "googlekey": RECAPTCHA_SITE_KEY, "pageurl": page_url, "invisible": 1, "json": 1})
    with urllib.request.urlopen(submit_url, timeout=30) as r:
        resp = json.loads(r.read())
    if resp.get("status") != 1:
        raise RuntimeError(f"2captcha submit failed: {resp}")
    captcha_id = resp["request"]
    poll_url = "https://2captcha.com/res.php?" + urllib.parse.urlencode({"key": api_key, "action": "get", "id": captcha_id, "json": 1})
    for attempt in range(24):
        time.sleep(5)
        result = None
        for retry in range(3):
            try:
                with urllib.request.urlopen(poll_url, timeout=30) as r:
                    result = json.loads(r.read())
                break
            except Exception as exc:  # noqa: BLE001
                if retry == 2:
                    raise
                log(f"2captcha poll error ({exc}), retry")
                time.sleep(3)
        if result.get("status") == 1:
            log(f"2captcha solved after {(attempt + 1) * 5}s")
            return result["request"]
        if result.get("request") != "CAPCHA_NOT_READY":
            raise RuntimeError(f"2captcha error: {result}")
    raise RuntimeError("2captcha timed out after 120s")


# --- login ---------------------------------------------------------------------

def login(page, cfg: dict) -> None:
    from playwright.sync_api import TimeoutError as PWTimeout
    page.goto(PORTAL_URL, wait_until="networkidle", timeout=60_000)
    try:
        btn = page.locator("button:has-text('Povoliť všetko'), #CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll")
        btn.first.wait_for(state="visible", timeout=5_000)
        btn.first.click()
        page.wait_for_load_state("networkidle", timeout=10_000)
    except Exception:  # noqa: BLE001
        pass
    try:
        user_input = page.locator("input#user")
        user_input.wait_for(state="visible", timeout=20_000)
        user_input.click()
        user_input.fill(cfg["user"])
        page.keyboard.press("Tab")
        page.locator("input#password").fill(cfg["password"])
        page.wait_for_timeout(500)
        login_result: dict = {}

        def _capture(response):
            if "security/login" in response.url:
                login_result["status"] = response.status
                try:
                    login_result["body"] = json.loads(response.text())
                except Exception:  # noqa: BLE001
                    login_result["body"] = {}

        page.on("response", _capture)
        token = solve_recaptcha(cfg["twocaptcha_api_key"], page.url)
        page.evaluate(f"window.__captchaCb && window.__captchaCb({json.dumps(token)})")
        for _ in range(60):
            if login_result:
                break
            page.wait_for_timeout(500)
        page.remove_listener("response", _capture)
        if login_result.get("status") != 200:
            raise RuntimeError(f"Login failed: HTTP {login_result.get('status')} {str(login_result.get('body'))[:200]}")
        page.goto("https://www.diportal.sk/portal/#/verejne/vitajte", wait_until="networkidle", timeout=30_000)
    except PWTimeout as exc:
        raise RuntimeError(f"Login timed out: {exc}") from exc


def get_csrf(page):
    for expr in ["window.csrfToken", "window.csrf_token", "document.querySelector('meta[name=\"csrf-token\"]')?.content",
                 "document.querySelector('meta[name=\"_csrf\"]')?.content"]:
        try:
            val = page.evaluate(expr)
            if val and isinstance(val, str) and len(val) > 6:
                return val
        except Exception:  # noqa: BLE001
            pass
    holder: dict = {}

    def _on_response(response):
        token = response.headers.get("x-csrf-token")
        if token and token.lower() != "required":
            holder["token"] = token

    page.on("response", _on_response)
    try:
        page.evaluate("""() => fetch('/portal/api/interval-data/getProfileData', {method: 'GET',
            headers: {'X-CSRF-Token': 'fetch', 'Accept': 'application/json'}, credentials: 'include'}).catch(() => null)""")
        page.wait_for_timeout(3_000)
    except Exception:  # noqa: BLE001
        pass
    page.remove_listener("response", _on_response)
    if holder.get("token"):
        return holder["token"]
    for cookie in page.context.cookies():
        if "csrf" in cookie["name"].lower():
            return cookie["value"]
    m = re.search(r'"csrfToken"\s*:\s*"([A-Za-z0-9+/=_\-]{8,})"', page.content())
    return m.group(1) if m else None


# --- API -----------------------------------------------------------------------

def post_json(page, url: str, payload: dict, csrf, label: str = "") -> dict:
    headers = {"X-CSRF": csrf} if csrf else {}
    result = page.evaluate(
        """async ([url, body, extraHeaders]) => {
            const resp = await fetch(url, {method: 'POST', credentials: 'include', body: body,
                headers: {'Content-Type': 'application/json', 'Accept': 'application/json, text/plain, */*', ...extraHeaders}});
            const text = await resp.text();
            return {status: resp.status, ok: resp.ok, text: text};
        }""", [url, json.dumps(payload), headers])
    if not result["ok"]:
        raise RuntimeError(f"API {label} HTTP {result['status']}: {result['text'][:300]}")
    if not result["text"].strip():
        raise RuntimeError(f"API {label} empty body")
    return json.loads(result["text"])


def fetch_profile(page, csrf, cfg, delivery_point_id: str, date_from: str, date_to: str, profile_role=None) -> dict:
    payload = {"filter": {"deliveryPointId": delivery_point_id, "from": date_from, "to": date_to,
                          "profileRole": profile_role, "loadProfileRoles": True},
               "businessPartnerId": cfg["business_partner_id"], "businessRoleId": "KZ", "source": "KOC"}
    return post_json(page, API_URL, payload, csrf, label=f"getProfileData dp={delivery_point_id} role={profile_role!r}")


def load_delivery_points(page, csrf, cfg) -> list[dict]:
    payload = {"filter": {"onlyActive": True, "smartMeterEnabled": None, "dateFrom": "", "dateTo": ""},
               "businessPartnerId": cfg["business_partner_id"], "businessRoleId": "KZ"}
    data = post_json(page, DELIVERY_POINTS_URL, payload, csrf, label="loadDeliveryPoints")
    out = []
    for p in data.get("data") or []:
        if not isinstance(p, dict):
            continue
        out.append({"id": str(p.get("deliveryPointId") or p.get("id") or ""), "eic": p.get("eic") or "",
                    "address": " ".join(str(p.get(k) or "") for k in ("street", "houseNumber", "city") if p.get(k)).strip()
                    or str(p.get("address") or ""), "name": str(p.get("name") or p.get("description") or ""),
                    "raw": {k: v for k, v in p.items() if isinstance(v, (str, int, float, bool))}})
    return out


# --- profile roles (odber vs dodávka) ---------------------------------------------

_GEN_MARKERS = ("2.8.", "dodav", "vyrob", "gener", "export", "product", "feed", "vystup")


def _fold(text) -> str:
    return str(text).lower().translate(str.maketrans("áäčďéíĺľňóôŕšťúýž", "aacdeillnoorstuyz"))


def role_code(role):
    if isinstance(role, dict):
        for key in ("roleId", "code", "id", "key", "value", "profileRole", "role", "obis", "name"):
            if role.get(key) not in (None, ""):
                return role[key]
        return role
    return role


def classify_role(role):
    texts = [_fold(v) for v in (role.values() if isinstance(role, dict) else [role]) if isinstance(v, str)]
    if any("jalov" in t for t in texts):
        return "reactive"
    if any(m in t for t in texts for m in _GEN_MARKERS):
        return "generation"
    return "consumption"


def discover_roles(data) -> list:
    by_key: dict = {}

    def walk(node, key=""):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, k)
        elif isinstance(node, list):
            lk = key.lower()
            if "role" in lk and node and all(isinstance(x, (str, dict)) for x in node):
                b = by_key.setdefault(lk, [])
                for x in node:
                    if x not in b:
                        b.append(x)
            else:
                for x in node:
                    walk(x, key)

    walk(data)
    for lk, roles in by_key.items():
        if "profile" in lk:
            return roles
    for lk, roles in by_key.items():
        if "business" not in lk:
            return roles
    return []


def daily_totals(data) -> dict:
    """{date: [kwh, intervals]} for every day in a response (kW × 0.25 h per 15-min value)."""
    try:
        days = data["data"]["profileData"]["dailyIntervalData"]
    except (KeyError, TypeError):
        return {}
    out = {}
    for day in days or []:
        d = day.get("date")
        if not d:
            continue
        kwh, n = 0.0, 0
        for iv in day.get("values", []):
            try:
                kwh += abs(float(iv.get("measuredValue"))) / 4
                n += 1
            except (TypeError, ValueError):
                pass
        if n:
            out[d] = [round(kwh, 3), n]
    return out


def collect(page, csrf, cfg, dp_id: str, dates: list[str], role, calls: list) -> dict:
    """Ranged call first; days it did not cover (or returned incomplete) one by one."""
    totals: dict = {}
    try:
        data = fetch_profile(page, csrf, cfg, dp_id, dates[0], dates[-1], role)
        calls.append(data)
        totals.update({d: v for d, v in daily_totals(data).items() if v[1] >= MIN_COMPLETE_INTERVALS})
    except Exception as exc:  # noqa: BLE001
        log(f"ranged call failed for {dp_id}: {exc}")
    missing = [d for d in dates if d not in totals][-MAX_DAY_CALLS:]
    failures = 0
    for d in missing:
        try:
            data = fetch_profile(page, csrf, cfg, dp_id, d, d, role)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            log(f"{dp_id} {d}: {exc}")
            if failures >= 3:
                break
            continue
        t = daily_totals(data).get(d)
        if t and t[1] >= MIN_COMPLETE_INTERVALS:
            totals[d] = t
    return totals


def main() -> int:
    cfg = json.loads(sys.stdin.read() or "{}")
    for k in ("user", "password", "business_partner_id", "twocaptcha_api_key"):
        if not cfg.get(k):
            print(json.dumps({"errors": [f"missing {k}"]}))
            return 2
    days = int(cfg.get("days") or 8)
    today = datetime.date.today()
    dates = [(today - datetime.timedelta(days=i)).isoformat() for i in range(days, 0, -1)]
    out = {"services": [], "delivery_points": None, "errors": []}
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth
    with sync_playwright() as pw:
        browser = context = None
        try:
            browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(user_agent=UA, locale="sk-SK", timezone_id="Europe/Bratislava")
            # Intercept ng2recaptcha so grecaptcha.render hands us the callback; we fire it with the
            # 2captcha token after the form is filled, so the POST carries the credentials too.
            context.add_init_script("""
                (function() {
                    window.__captchaCb = null;
                    var _stored = null;
                    Object.defineProperty(window, 'ng2recaptchaloaded', {
                        configurable: true,
                        get: function() { return _stored; },
                        set: function(origFn) {
                            _stored = function() {
                                if (window.grecaptcha && window.grecaptcha.render) {
                                    window.grecaptcha.render = function(el, params) {
                                        if (params && params.callback) { window.__captchaCb = params.callback; }
                                        return 0;
                                    };
                                }
                                origFn();
                            };
                        }
                    });
                })();
            """)
            page = context.new_page()
            Stealth().apply_stealth_sync(page)
            login(page, cfg)
            log("login OK")
            csrf = get_csrf(page)
            try:
                out["delivery_points"] = load_delivery_points(page, csrf, cfg)
                log(f"delivery points: {len(out['delivery_points'])}")
            except Exception as exc:  # noqa: BLE001
                out["errors"].append(f"loadDeliveryPoints: {exc}")
            if cfg.get("explore"):
                for s in cfg.get("services") or []:
                    try:
                        data = fetch_profile(page, csrf, cfg, s["delivery_point_id"], dates[-1], dates[-1])
                        out.setdefault("explore", {})[s["delivery_point_id"]] = data
                    except Exception as exc:  # noqa: BLE001
                        out["errors"].append(f"explore {s['delivery_point_id']}: {exc}")
            for s in cfg.get("services") or []:
                dp = str(s["delivery_point_id"])
                entry = {"service_id": s["service_id"], "consumption": {}, "generation": {}}
                calls: list = []
                try:
                    entry["consumption"] = collect(page, csrf, cfg, dp, dates, None, calls)
                except Exception as exc:  # noqa: BLE001
                    out["errors"].append(f"{dp} odber: {exc}")
                gen_ref = str(s.get("generation_ref") or "").strip()
                try:
                    if gen_ref:
                        # either a profile role code on the same delivery point, or a separate
                        # delivery point id (PV "malý zdroj" billed on its own EIC)
                        if gen_ref.isdigit() and gen_ref != dp:
                            entry["generation"] = collect(page, csrf, cfg, gen_ref, dates, None, calls)
                        else:
                            entry["generation"] = collect(page, csrf, cfg, dp, dates, gen_ref, calls)
                    elif calls:
                        roles = [r for r in discover_roles(calls[0]) if classify_role(r) == "generation"]
                        if roles:
                            entry["generation"] = collect(page, csrf, cfg, dp, dates, role_code(roles[0]), calls)
                            entry["generation_role"] = role_code(roles[0])
                except Exception as exc:  # noqa: BLE001
                    out["errors"].append(f"{dp} dodávka: {exc}")
                out["services"].append(entry)
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"fatal: {exc}")
            print(json.dumps(out, ensure_ascii=False))
            return 1
        finally:
            try:
                if context:
                    context.close()
                if browser:
                    browser.close()
            except Exception:  # noqa: BLE001
                pass
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
