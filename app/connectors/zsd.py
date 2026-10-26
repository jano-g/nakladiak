"""ZSD diportal.sk connector: 15-minute interval data (odber 1.8.0 and dodávka 2.8.0) for every
delivery point of one customer account, aggregated to kWh per day into `readings`.

The portal (SAP, F5 bot protection, reCAPTCHA) only talks to a real browser, so the fetch runs
headless Chromium via Playwright in a SUBPROCESS (`python -m app.connectors.zsd_fetch`, credentials
over stdin, JSON over stdout). Ported from jano-g/spotreba_bela/fetch.py (2026-06..10)."""
import json
import logging
import subprocess
import sys
from datetime import timedelta

from .. import db, settings, util

log = logging.getLogger(__name__)
NAME = "zsd"
LABEL = "ZSD diportal (elektrina, 15-min dáta)"
TIMEOUT_S = 900


def is_configured() -> bool:
    return bool(settings.get("zsd_user") and settings.get("zsd_password") and settings.get("zsd_business_partner_id")
                and settings.get("twocaptcha_api_key"))


def mapped_services() -> list[dict]:
    return db.rows(db.q("SELECT * FROM services WHERE active=1 AND connector='zsd' AND connector_ref<>''"))


def delivery_points() -> list[dict]:
    try:
        return json.loads(db.get_setting("zsd_delivery_points", "[]"))
    except ValueError:
        return []


def _config(days: int, explore: bool = False) -> dict:
    return {
        "user": settings.get("zsd_user"), "password": settings.get("zsd_password"),
        "business_partner_id": settings.get("zsd_business_partner_id"),
        "twocaptcha_api_key": settings.get("twocaptcha_api_key"),
        "days": days, "explore": explore,
        "services": [{"service_id": s["id"], "delivery_point_id": s["connector_ref"], "generation_ref": s["connector_ref2"]}
                     for s in mapped_services()],
    }


def run(days: int = 8, explore: bool = False) -> dict:
    """Spawn the fetch, store readings, record the run. Raises on failure (scheduler alerts)."""
    if not is_configured():
        raise RuntimeError("ZSD nie je nastavené (prihlásenie, business partner, 2captcha kľúč).")
    run_id = db.run("INSERT INTO connector_runs(connector,started_at) VALUES(?,?)", (NAME, db.now_iso()))
    try:
        proc = subprocess.run([sys.executable, "-m", "app.connectors.zsd_fetch"], input=json.dumps(_config(days, explore)),
                              capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        _finish(run_id, False, "ZSD: fetch prekročil 15 minút.")
        raise RuntimeError("ZSD: fetch prekročil 15 minút.")
    tail = (proc.stderr or "")[-1500:]
    if proc.returncode != 0:
        msg = f"ZSD fetch skončil chybou ({proc.returncode})."
        _finish(run_id, False, msg, tail)
        log.warning("zsd fetch failed: %s", tail)
        raise RuntimeError(msg + " " + tail.strip().splitlines()[-1][:200] if tail.strip() else msg)
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        _finish(run_id, False, "ZSD fetch nevrátil JSON.", tail)
        raise RuntimeError("ZSD fetch nevrátil JSON.")
    stored = _store(result)
    if result.get("delivery_points") is not None:
        db.set_setting("zsd_delivery_points", json.dumps(result["delivery_points"], ensure_ascii=False))
    msg = f"OK: {stored} denných hodnôt, {len(result.get('services') or [])} odberných miest."
    errors = result.get("errors") or []
    if errors:
        msg += f" Chyby: {len(errors)}."
    _finish(run_id, not errors or stored > 0, msg, "\n".join(errors)[:2000])
    db.set_setting("zsd_last_ok", db.now_iso())
    return {"stored": stored, "errors": errors, "message": msg}


def _store(result: dict) -> int:
    n = 0
    now = db.now_iso()
    with db.tx():
        for s in result.get("services") or []:
            sid = s.get("service_id")
            if not db.q1("SELECT 1 FROM services WHERE id=?", (sid,)):
                continue
            for kind in ("consumption", "generation"):
                for day, (kwh, intervals) in (s.get(kind) or {}).items():
                    if not util.parse_date(day) or kwh is None:
                        continue
                    db.run("INSERT INTO readings(service_id,date,kind,value,intervals,source,updated_at) VALUES(?,?,?,?,?,?,?) "
                           "ON CONFLICT(service_id,date,kind) DO UPDATE SET value=excluded.value, intervals=excluded.intervals, updated_at=excluded.updated_at",
                           (sid, day, kind, round(float(kwh), 3), int(intervals or 0), NAME, now))
                    n += 1
    return n


def _finish(run_id: int, ok: bool, message: str, details: str = "") -> None:
    db.run("UPDATE connector_runs SET finished_at=?, ok=?, message=?, details=? WHERE id=?",
           (db.now_iso(), 1 if ok else 0, message[:300], details[:4000], run_id))


def last_run() -> dict | None:
    return db.row(db.q1("SELECT * FROM connector_runs WHERE connector=? ORDER BY id DESC LIMIT 1", (NAME,)))


def missing_days(service_id: int, days: int) -> list[str]:
    today = util.today_local()
    have = {r["date"] for r in db.q("SELECT date FROM readings WHERE service_id=? AND kind='consumption' AND date>=?",
                                     (service_id, (today - timedelta(days=days)).isoformat()))}
    return [d.isoformat() for d in (today - timedelta(days=i) for i in range(1, days + 1)) if d.isoformat() not in have]
