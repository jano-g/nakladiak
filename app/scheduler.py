"""One daemon thread, one tick every 30 s. Everything is idempotent — a missed tick is caught
up on the next one, a repeated tick does nothing twice (settings 'last_*' markers,
reminders_sent). Heavy jobs (ZSD browser fetch, IMAP) never run at the same time."""
import logging
import threading
import time
from datetime import timedelta

from . import db, settings, util
from .services import alerts, bank, costs, documents, mailbox, notify
from .connectors import zsd

log = logging.getLogger(__name__)
_stop = threading.Event()
_heavy = threading.Lock()
last_tick: float = 0.0
_last_imap: float = 0.0
IMAP_EVERY = 15 * 60


def _guard(name: str, fn, *args) -> None:
    try:
        fn(*args)
    except Exception as exc:  # noqa: BLE001
        log.exception("job %s failed", name)
        alerts.alert(f"job:{name}", f"job {name} zlyhal", str(exc)[:300])


def process_documents() -> None:
    for _ in range(5):
        if not documents.process_next():
            break


def poll_mailbox(force: bool = False) -> None:
    global _last_imap
    if settings.get("imap_enabled") != "1" and not force:
        return
    if not force and time.time() - _last_imap < IMAP_EVERY:
        return
    if not mailbox.is_configured():
        return
    _last_imap = time.time()
    if not _heavy.acquire(blocking=False):
        return
    try:
        res = mailbox.poll_safe()
        if res and res.get("stored"):
            log.info("imap: %s", res)
    finally:
        _heavy.release()


def run_zsd(force: bool = False, days: int = 8) -> dict | None:
    """Daily at `zsd_time`, once per day, only when at least one service is mapped."""
    now_local = util.now_local()
    today = now_local.date().isoformat()
    if not force:
        if settings.get("zsd_enabled") != "1" or not zsd.is_configured() or not zsd.mapped_services():
            return None
        if now_local.strftime("%H:%M") < (settings.get("zsd_time") or "14:35"):
            return None
        if db.get_setting("last_zsd_day", "") == today:
            return None
    if not _heavy.acquire(blocking=False):
        return None
    try:
        db.set_setting("last_zsd_day", today)
        try:
            res = zsd.run(days=days)
        except Exception as exc:  # noqa: BLE001
            # retried tomorrow; a second failure in a row is worth a push
            prev = db.get_setting("zsd_fail_count", "0")
            n = int(prev or 0) + 1
            db.set_setting("zsd_fail_count", str(n))
            if n >= 2:
                alerts.alert("zsd", "ZSD sa nepodarilo stiahnuť", str(exc)[:300])
                notify.broadcast("ZSD dáta sa nepodarilo stiahnuť", str(exc)[:200], tags=["warning"])
            raise
        db.set_setting("zsd_fail_count", "0")
        return res
    finally:
        _heavy.release()


def _once(key: str) -> bool:
    """True the first time `key` is seen (persisted) — for once-a-day/-week reminders."""
    if db.q1("SELECT 1 FROM reminders_sent WHERE key=?", (key,)):
        return False
    db.run("INSERT INTO reminders_sent(key,sent_at) VALUES(?,?)", (key, db.now_iso()))
    return True


def reminders() -> None:
    now_local = util.now_local()
    if now_local.hour < 8:
        return
    today = now_local.date()
    # 1. invoices due within 3 days or overdue, unpaid
    for inv in costs.due_invoices(today, days=3):
        if _once(f"due:{inv['id']}:{today.isoformat()[:7]}"):
            when = "po splatnosti" if inv["overdue"] else f"splatná {util.fmt_date(util.parse_date(inv['due_at']))}"
            notify.broadcast(f"Faktúra {when}", f"{inv['supplier']} {inv['service']} {inv['place'] or ''}: {util.fmt_eur(inv['amount'])}",
                             click=f"/#/documents/{inv['document_id']}", tags=["moneybag"])
    # 2. statement reminder every N days
    try:
        every = int(settings.get("statement_reminder_days") or "30")
    except ValueError:
        every = 30
    if every > 0:
        last = db.get_setting("last_statement_at", "") or db.get_setting("first_start_at", "")
        last_d = util.parse_date(last) if last else None
        if last_d and (today - last_d).days >= every and _once(f"statement:{today.isoformat()}"):
            notify.broadcast("Nahraj výpis z účtu", f"Posledný výpis je z {util.fmt_date(last_d)}. Nahraj nový, aby sa zarátali "
                             "platby záhradníkovi, správcovi a upratovanie.", click="/#/upload", tags=["bank"])
    # 3. weekly consumption overview on Monday
    if today.weekday() == 0 and _once(f"weekly:{today.isoformat()}"):
        lines = []
        for s in zsd.mapped_services():
            wk = costs.service_consumption(s["id"], today - timedelta(days=7), today - timedelta(days=1))
            prev = costs.service_consumption(s["id"], today - timedelta(days=14), today - timedelta(days=8))
            if not wk["days"]:
                continue
            p = db.q1("SELECT name FROM places WHERE id=?", (s["place_id"],))
            delta = ""
            if prev["days"] and prev["value"]:
                delta = f" ({(wk['value'] / prev['value'] - 1) * 100:+.0f} % oproti minulému týždňu)"
            lines.append(f"{p['name'] if p else ''}: {wk['value']:.1f} kWh{delta}")
        if lines:
            notify.broadcast("Spotreba za minulý týždeň", "\n".join(lines), click="/#/", tags=["electric_plug"])


def housekeeping() -> None:
    if _once(f"housekeeping:{util.today_local().isoformat()}"):
        db.run("DELETE FROM history WHERE at<?", ((util.now_local() - timedelta(days=730)).isoformat(),))
        db.run("DELETE FROM reminders_sent WHERE sent_at<?", ((util.now_local() - timedelta(days=400)).isoformat(),))


def tick() -> None:
    global last_tick
    _guard("documents", process_documents)
    _guard("mailbox", poll_mailbox)
    _guard("zsd", run_zsd)
    _guard("reminders", reminders)
    _guard("housekeeping", housekeeping)
    last_tick = time.time()


def _loop() -> None:
    time.sleep(5)
    while not _stop.is_set():
        tick()
        db.close()
        _stop.wait(30)


def start() -> None:
    if not db.get_setting("first_start_at", ""):
        db.set_setting("first_start_at", db.now_iso())
    threading.Thread(target=_loop, name="nakladiak-scheduler", daemon=True).start()


def stop() -> None:
    _stop.set()


def healthy() -> bool:
    return last_tick > 0 and time.time() - last_tick < 300
