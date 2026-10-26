"""JSON API for the SPA. Every write: X-Requested-With (middleware), current_user(), db.tx(),
db.log_history(). Slovak error messages go straight to the toast."""
import ipaddress
import json
import logging
import re
import threading
from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from .. import auth, config, db, settings, util
from ..connectors import zsd
from ..deps import ApiError, admin_user, current_user, json_body, public_user
from ..services import bank, costs, documents, extract, mailbox, mailer, ntfy
from ..services.costs import SERVICE_LABELS

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

PLACE_KINDS = {"byt": "Byt", "dom": "Dom", "chalupa": "Chalupa", "pozemok": "Pozemok", "ine": "Iné"}
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MODEL_RE = re.compile(r"^[a-z0-9.-]{3,60}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
USERNAME_RE = re.compile(r"^[a-z0-9._-]{2,40}$")

ACTION_LABELS = {
    "login": "Prihlásenie", "login_failed": "Neúspešné prihlásenie", "password_changed": "Zmena hesla",
    "password_set_via_link": "Heslo nastavené cez odkaz", "password_reset_requested": "Žiadosť o nové heslo",
    "password_reset_cli": "Heslo zmenené cez CLI", "logout_everywhere": "Odhlásenie všetkých zariadení",
    "user_created": "Pridal(a) používateľa", "user_updated": "Upravil(a) používateľa", "invite_sent": "Poslal(a) pozvánku",
    "mail_failed": "Mail sa nepodarilo poslať", "ntfy_failed": "Notifikácia sa nepodarila",
    "place_created": "Pridal(a) miesto", "place_updated": "Upravil(a) miesto", "place_archived": "Archivoval(a) miesto",
    "service_created": "Pridal(a) službu", "service_updated": "Upravil(a) službu", "service_deleted": "Odstránil(a) službu",
    "document_uploaded": "Nahral(a) dokument", "document_reviewed": "Potvrdil(a) dokument", "document_deleted": "Zmazal(a) dokument",
    "document_reprocess": "Znova prečítať dokument", "transaction_assigned": "Zaradil(a) platbu", "cost_created": "Pridal(a) výdavok",
    "cost_deleted": "Zmazal(a) výdavok", "rule_deleted": "Zmazal(a) pravidlo", "settings_updated": "Zmenil(a) nastavenia",
    "profile_updated": "Upravil(a) profil", "connector_run": "Spustil(a) konektor", "mailbox_poll": "Skontroloval(a) schránku",
    "invoice_paid": "Označil(a) faktúru ako zaplatenú",
}


def _ip(request: Request) -> str:
    return auth.client_ip(request)


def _int(v, name: str, lo: int | None = None, hi: int | None = None, allow_none=False):
    if v in (None, ""):
        if allow_none:
            return None
        raise ApiError(f"Chýba {name}.")
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ApiError(f"{name}: očakávam celé číslo.") from None
    if (lo is not None and n < lo) or (hi is not None and n > hi):
        raise ApiError(f"{name}: mimo rozsahu.")
    return n


def _money(v, name: str, allow_none=True):
    f = util.to_float(v)
    if f is None:
        if allow_none and v in (None, ""):
            return None
        raise ApiError(f"{name}: očakávam číslo.")
    if abs(f) > 1_000_000:
        raise ApiError(f"{name}: priveľká hodnota.")
    return round(f, 4)


def _date(v, name: str, allow_none=True):
    if v in (None, ""):
        if allow_none:
            return None
        raise ApiError(f"Chýba {name}.")
    if not util.parse_date(v):
        raise ApiError(f"{name}: očakávam dátum YYYY-MM-DD.")
    return str(v)[:10]


# --- me / meta -------------------------------------------------------------------

@router.get("/me")
def me(request: Request):
    u = current_user(request)
    places = db.rows(db.q("SELECT id,name,kind,color FROM places WHERE archived=0 ORDER BY sort, id"))
    return {"user": public_user(u) | {"ntfy_topic": u.get("ntfy_topic", ""), "notify_ntfy": bool(u.get("notify_ntfy", 1)),
                                      "notify_email": bool(u.get("notify_email", 0))},
            "today": util.today_local().isoformat(), "places": places, "pending": costs.pending_counts(),
            "claude_ready": bool(settings.get("anthropic_api_key")), "mailbox_ready": mailbox.is_configured(),
            "changelog_new": _latest_changelog_date() > (u.get("seen_changelog") or "")}


@router.get("/meta")
def meta(request: Request):
    current_user(request)
    return {"service_kinds": [{"id": k, "label": SERVICE_LABELS[k]} for k in extract.SERVICE_KINDS],
            "categories": [{"id": k, "label": SERVICE_LABELS.get(k, k)} for k in bank.CATEGORIES],
            "place_kinds": [{"id": k, "label": v} for k, v in PLACE_KINDS.items()],
            "doc_kinds": [{"id": "auto", "label": "Nechaj appku rozhodnúť"}, {"id": "faktura", "label": "Faktúra / vyúčtovanie"},
                          {"id": "uctenka", "label": "Účtenka"}, {"id": "vypis", "label": "Výpis z účtu"}, {"id": "ine", "label": "Iné"}],
            "connectors": [{"id": zsd.NAME, "label": zsd.LABEL, "configured": zsd.is_configured(),
                            "delivery_points": zsd.delivery_points()}]}


# --- dashboard -----------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(request: Request, month: str = ""):
    current_user(request)
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month or ""):
        month = util.today_local().strftime("%Y-%m")
    return costs.dashboard(month)


# --- places --------------------------------------------------------------------------

def _place_payload(data: dict, existing: dict | None = None) -> dict:
    name = util.clean_text(data.get("name", existing["name"] if existing else ""), 60)
    if not name:
        raise ApiError("Miesto potrebuje názov.")
    kind = data.get("kind", existing["kind"] if existing else "byt")
    if kind not in PLACE_KINDS:
        raise ApiError("Neznámy typ miesta.")
    color = data.get("color", existing["color"] if existing else "#3b6ea5") or "#3b6ea5"
    if not COLOR_RE.match(color):
        raise ApiError("Farba musí byť #rrggbb.")
    return {"name": name, "kind": kind, "color": color,
            "address": util.clean_text(data.get("address", existing["address"] if existing else ""), 160),
            "sort": _int(data.get("sort", existing["sort"] if existing else 0), "poradie", -1000, 1000)}


def _place_out(p: dict) -> dict:
    return {k: p[k] for k in ("id", "name", "kind", "address", "color", "sort", "archived")} | {"kind_label": PLACE_KINDS.get(p["kind"], p["kind"])}


@router.get("/places")
def places_list(request: Request, archived: int = 0):
    current_user(request)
    rows = db.rows(db.q("SELECT * FROM places WHERE archived=? ORDER BY sort, id", (1 if archived else 0,)))
    services = db.rows(db.q("SELECT * FROM services WHERE active=1 ORDER BY kind, id"))
    out = []
    for p in rows:
        o = _place_out(p)
        o["services"] = [_service_out(s) for s in services if s["place_id"] == p["id"]]
        out.append(o)
    return {"places": out}


@router.post("/places")
async def place_create(request: Request):
    u = current_user(request)
    data = _place_payload(await json_body(request))
    with db.tx():
        pid = db.run("INSERT INTO places(name,kind,address,color,sort,created_at) VALUES(?,?,?,?,?,?)",
                     (data["name"], data["kind"], data["address"], data["color"], data["sort"], db.now_iso()))
        db.log_history(u["id"], "place_created", {"place_id": pid, "name": data["name"]}, _ip(request))
    return _place_out(db.row(db.q1("SELECT * FROM places WHERE id=?", (pid,))))


@router.get("/places/{pid}")
def place_get(request: Request, pid: int):
    current_user(request)
    p = db.row(db.q1("SELECT * FROM places WHERE id=?", (pid,)))
    if not p:
        raise ApiError("Miesto neexistuje.", 404)
    out = _place_out(p)
    out["services"] = [_service_out(s) for s in db.rows(db.q("SELECT * FROM services WHERE place_id=? ORDER BY active DESC, kind, id", (pid,)))]
    today = util.today_local()
    first = util.add_months(util.month_start(today), -11)
    out["months"] = costs.monthly_history(first, util.month_start(today))
    out["costs"] = _costs_rows("WHERE c.place_id=? ORDER BY c.date DESC, c.id DESC LIMIT 100", (pid,))
    out["documents"] = [_doc_out(d) for d in db.rows(db.q("SELECT * FROM documents WHERE place_id=? ORDER BY id DESC LIMIT 50", (pid,)))]
    return out


@router.put("/places/{pid}")
async def place_update(request: Request, pid: int):
    u = current_user(request)
    p = db.row(db.q1("SELECT * FROM places WHERE id=?", (pid,)))
    if not p:
        raise ApiError("Miesto neexistuje.", 404)
    body = await json_body(request)
    data = _place_payload(body, p)
    archived = 1 if body.get("archived") else (0 if "archived" in body else p["archived"])
    with db.tx():
        db.run("UPDATE places SET name=?, kind=?, address=?, color=?, sort=?, archived=? WHERE id=?",
               (data["name"], data["kind"], data["address"], data["color"], data["sort"], archived, pid))
        db.log_history(u["id"], "place_archived" if archived and not p["archived"] else "place_updated", {"place_id": pid}, _ip(request))
    return _place_out(db.row(db.q1("SELECT * FROM places WHERE id=?", (pid,))))


# --- services --------------------------------------------------------------------------

def _service_out(s: dict) -> dict:
    o = {k: s[k] for k in ("id", "place_id", "kind", "supplier", "label", "identifier", "identifier2", "unit", "unit_price",
                           "fixed_monthly", "monthly_estimate", "connector", "connector_ref", "connector_ref2", "active", "note")}
    o["kind_label"] = SERVICE_LABELS.get(s["kind"], s["kind"])
    return o


def _service_payload(data: dict, existing: dict | None = None) -> dict:
    g = lambda k, d="": data.get(k, existing[k] if existing else d)  # noqa: E731
    kind = g("kind", "elektrina")
    if kind not in extract.SERVICE_KINDS:
        raise ApiError("Neznámy druh služby.")
    place_id = _int(g("place_id"), "miesto")
    if not db.q1("SELECT 1 FROM places WHERE id=?", (place_id,)):
        raise ApiError("Miesto neexistuje.")
    connector = g("connector", "") or ""
    if connector not in ("", zsd.NAME):
        raise ApiError("Neznámy konektor.")
    unit = util.clean_text(g("unit", ""), 10)
    if kind == "elektrina" and not unit:
        unit = "kWh"
    if kind in ("plyn", "voda") and not unit:
        unit = "m3"
    return {"place_id": place_id, "kind": kind, "supplier": util.clean_text(g("supplier"), 120),
            "label": util.clean_text(g("label"), 60), "identifier": util.clean_text(g("identifier"), 60),
            "identifier2": util.clean_text(g("identifier2"), 60), "unit": unit,
            "unit_price": _money(g("unit_price", None), "cena za jednotku"),
            "fixed_monthly": _money(g("fixed_monthly", None), "fixný mesačný poplatok"),
            "monthly_estimate": _money(g("monthly_estimate", None), "mesačná záloha"),
            "connector": connector, "connector_ref": util.clean_text(g("connector_ref"), 60),
            "connector_ref2": util.clean_text(g("connector_ref2"), 60), "note": util.clean_text(g("note"), 300, multiline=True),
            "active": 1 if g("active", 1) in (1, True, "1") else 0}


@router.post("/services")
async def service_create(request: Request):
    u = current_user(request)
    d = _service_payload(await json_body(request))
    with db.tx():
        sid = db.run("INSERT INTO services(place_id,kind,supplier,label,identifier,identifier2,unit,unit_price,fixed_monthly,"
                     "monthly_estimate,connector,connector_ref,connector_ref2,active,note,created_at,updated_at) "
                     "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (d["place_id"], d["kind"], d["supplier"], d["label"], d["identifier"], d["identifier2"], d["unit"],
                      d["unit_price"], d["fixed_monthly"], d["monthly_estimate"], d["connector"], d["connector_ref"],
                      d["connector_ref2"], d["active"], d["note"], db.now_iso(), db.now_iso()))
        db.log_history(u["id"], "service_created", {"service_id": sid, "kind": d["kind"]}, _ip(request))
    return _service_out(db.row(db.q1("SELECT * FROM services WHERE id=?", (sid,))))


@router.get("/services/{sid}")
def service_get(request: Request, sid: int, months: int = 12):
    current_user(request)
    s = db.row(db.q1("SELECT * FROM services WHERE id=?", (sid,)))
    if not s:
        raise ApiError("Služba neexistuje.", 404)
    out = _service_out(s)
    today = util.today_local()
    months = max(1, min(36, months))
    start = util.add_months(util.month_start(today), -(months - 1))
    out["invoices"] = [_invoice_out(i) for i in db.rows(db.q("SELECT * FROM invoices WHERE service_id=? ORDER BY COALESCE(period_to,issued_at) DESC, id DESC LIMIT 60", (sid,)))]
    out["costs"] = _costs_rows("WHERE c.service_id=? ORDER BY c.date DESC, c.id DESC LIMIT 100", (sid,))
    out["readings"] = costs.series(sid, today - timedelta(days=90), today)
    out["monthly_readings"] = db.rows(db.q("SELECT substr(date,1,7) ym, kind, ROUND(SUM(value),2) v, COUNT(*) n FROM readings "
                                           "WHERE service_id=? AND date>=? GROUP BY ym, kind ORDER BY ym", (sid, start.isoformat())))
    out["week"] = costs.service_consumption(sid, today - timedelta(days=6), today)
    out["estimate"] = costs.estimate_for_month(s, today.strftime("%Y-%m"), today)
    return out


@router.put("/services/{sid}")
async def service_update(request: Request, sid: int):
    u = current_user(request)
    s = db.row(db.q1("SELECT * FROM services WHERE id=?", (sid,)))
    if not s:
        raise ApiError("Služba neexistuje.", 404)
    d = _service_payload(await json_body(request), s)
    with db.tx():
        db.run("UPDATE services SET place_id=?,kind=?,supplier=?,label=?,identifier=?,identifier2=?,unit=?,unit_price=?,fixed_monthly=?,"
               "monthly_estimate=?,connector=?,connector_ref=?,connector_ref2=?,active=?,note=?,updated_at=? WHERE id=?",
               (d["place_id"], d["kind"], d["supplier"], d["label"], d["identifier"], d["identifier2"], d["unit"], d["unit_price"],
                d["fixed_monthly"], d["monthly_estimate"], d["connector"], d["connector_ref"], d["connector_ref2"], d["active"],
                d["note"], db.now_iso(), sid))
        db.log_history(u["id"], "service_updated", {"service_id": sid}, _ip(request))
    return _service_out(db.row(db.q1("SELECT * FROM services WHERE id=?", (sid,))))


@router.delete("/services/{sid}")
def service_delete(request: Request, sid: int):
    u = current_user(request)
    s = db.row(db.q1("SELECT * FROM services WHERE id=?", (sid,)))
    if not s:
        raise ApiError("Služba neexistuje.", 404)
    used = db.q1("SELECT 1 FROM costs WHERE service_id=? LIMIT 1", (sid,)) or db.q1("SELECT 1 FROM invoices WHERE service_id=? LIMIT 1", (sid,))
    with db.tx():
        if used:
            db.run("UPDATE services SET active=0, updated_at=? WHERE id=?", (db.now_iso(), sid))
        else:
            db.run("DELETE FROM readings WHERE service_id=?", (sid,))
            db.run("UPDATE rules SET service_id=NULL WHERE service_id=?", (sid,))
            db.run("UPDATE documents SET service_id=NULL WHERE service_id=?", (sid,))
            db.run("DELETE FROM services WHERE id=?", (sid,))
        db.log_history(u["id"], "service_deleted", {"service_id": sid, "deactivated": bool(used)}, _ip(request))
    return {"ok": True, "deactivated": bool(used)}


# --- documents -----------------------------------------------------------------------

def _doc_out(d: dict, full: bool = False) -> dict:
    data = json.loads(d["extracted"]) if d.get("extracted") else (d.get("data") if isinstance(d.get("data"), dict) else None)
    o = {k: d[k] for k in ("id", "kind", "status", "source", "filename", "mime", "size", "received_at", "error", "attempts",
                           "place_id", "service_id", "mail_from", "mail_subject", "review_note", "created_at", "updated_at")}
    o["summary"] = (data or {}).get("summary", "") if data else ""
    o["doc_kind"] = (data or {}).get("doc_kind") if data else None
    o["supplier"] = (data or {}).get("supplier") if data else None
    o["match_how"] = (data or {}).get("match_how") if data else None
    if full and data:
        o["data"] = {k: v for k, v in data.items() if not k.startswith("_")}
        o["suggested_service_id"] = data.get("matched_service_id")
        o["suggested_place_id"] = data.get("matched_place_id")
        o["match_confidence"] = data.get("match_confidence")
    if full:
        o["invoice"] = _invoice_out(db.row(db.q1("SELECT * FROM invoices WHERE document_id=?", (d["id"],)))) if db.q1("SELECT 1 FROM invoices WHERE document_id=?", (d["id"],)) else None
        o["costs"] = _costs_rows("WHERE c.document_id=? ORDER BY c.date DESC", (d["id"],))
        o["transactions"] = db.rows(db.q("SELECT * FROM transactions WHERE document_id=? ORDER BY date DESC, id DESC LIMIT 500", (d["id"],)))
    return o


def _invoice_out(i: dict | None) -> dict | None:
    if not i:
        return None
    return {k: i[k] for k in ("id", "document_id", "service_id", "supplier", "number", "kind", "issued_at", "period_from", "period_to",
                              "due_at", "total", "to_pay", "advances", "currency", "consumption", "unit", "unit_price",
                              "variable_symbol", "paid_at")}


def _costs_rows(where: str, params) -> list[dict]:
    return db.rows(db.q(
        "SELECT c.*, p.name place_name, s.kind service_kind, s.label service_label FROM costs c "
        "LEFT JOIN places p ON p.id=c.place_id LEFT JOIN services s ON s.id=c.service_id " + where, params))


@router.get("/documents")
def documents_list(request: Request, status: str = "", before: int = 0, limit: int = 50, place_id: int = 0):
    current_user(request)
    limit = max(1, min(200, limit))
    where, params = [], []
    if status:
        if status == "open":
            where.append("status IN ('new','processing','needs_review','error')")
        else:
            where.append("status=?"); params.append(status)
    if before:
        where.append("id<?"); params.append(before)
    if place_id:
        where.append("place_id=?"); params.append(place_id)
    sql = "SELECT * FROM documents" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return {"documents": [_doc_out(d) for d in db.rows(db.q(sql, params))]}


@router.post("/documents")
async def document_upload(request: Request, file: UploadFile = File(...), kind: str = Form("auto"), hint: str = Form(""),
                          place_id: str = Form("")):
    u = current_user(request)
    try:
        if int(request.headers.get("content-length", "0")) > config.MAX_UPLOAD_BYTES + 65536:
            raise ApiError("Súbor je väčší ako 25 MB.", 413)
    except ValueError:
        pass
    data = await file.read()
    try:
        doc, created = documents.store(file.filename or "dokument", data, file.content_type or "", "upload", user_id=u["id"],
                                       kind=kind, hint=hint)
    except documents.DocError as exc:
        raise ApiError(str(exc)) from None
    pid = _int(place_id, "miesto", allow_none=True)
    if created and pid and db.q1("SELECT 1 FROM places WHERE id=?", (pid,)):
        db.run("UPDATE documents SET place_id=? WHERE id=?", (pid, doc["id"]))
    db.log_history(u["id"], "document_uploaded", {"document_id": doc["id"], "filename": doc["filename"], "duplicate": not created}, _ip(request))
    if created:
        threading.Thread(target=_process_bg, args=(doc["id"],), daemon=True).start()
    return {"document": _doc_out(documents.load(doc["id"])), "duplicate": not created}


def _process_bg(doc_id: int) -> None:
    try:
        documents.process_next_for(doc_id) if hasattr(documents, "process_next_for") else documents.process(doc_id)
    except Exception:  # noqa: BLE001
        log.exception("background processing of %s failed", doc_id)
    finally:
        db.close()


@router.get("/documents/{did}")
def document_get(request: Request, did: int):
    current_user(request)
    d = db.row(db.q1("SELECT * FROM documents WHERE id=?", (did,)))
    if not d:
        raise ApiError("Dokument neexistuje.", 404)
    return _doc_out(d, full=True)


@router.get("/documents/{did}/file")
def document_file(request: Request, did: int):
    current_user(request)
    d = documents.load(did)
    if not d:
        raise ApiError("Dokument neexistuje.", 404)
    path = documents.file_path(d)
    if not path.is_file():
        raise ApiError("Súbor chýba na disku.", 404)
    return FileResponse(str(path), media_type=d["mime"], headers={"Content-Disposition": "inline", "Cache-Control": "private, no-store"})


@router.post("/documents/{did}/review")
async def document_review(request: Request, did: int):
    u = current_user(request)
    body = await json_body(request)
    try:
        doc = documents.review(did, u["id"], place_id=_int(body.get("place_id"), "miesto", allow_none=True),
                               service_id=_int(body.get("service_id"), "služba", allow_none=True),
                               category=str(body.get("category") or ""), kind=str(body.get("kind") or ""),
                               remember=bool(body.get("remember", True)))
    except documents.DocError as exc:
        raise ApiError(str(exc)) from None
    return _doc_out(doc, full=True)


@router.post("/documents/{did}/reprocess")
async def document_reprocess(request: Request, did: int):
    u = current_user(request)
    body = await json_body(request)
    if not documents.load(did):
        raise ApiError("Dokument neexistuje.", 404)
    documents.reprocess(did, hint=str(body.get("hint") or ""))
    db.log_history(u["id"], "document_reprocess", {"document_id": did}, _ip(request))
    threading.Thread(target=_process_bg, args=(did,), daemon=True).start()
    return _doc_out(documents.load(did))


@router.delete("/documents/{did}")
def document_delete(request: Request, did: int):
    u = current_user(request)
    if not documents.load(did):
        raise ApiError("Dokument neexistuje.", 404)
    documents.delete(did)
    db.log_history(u["id"], "document_deleted", {"document_id": did}, _ip(request))
    return {"ok": True}


@router.post("/invoices/{iid}/paid")
async def invoice_paid(request: Request, iid: int):
    u = current_user(request)
    body = await json_body(request)
    inv = db.row(db.q1("SELECT * FROM invoices WHERE id=?", (iid,)))
    if not inv:
        raise ApiError("Faktúra neexistuje.", 404)
    paid = None if body.get("paid") is False else (_date(body.get("date"), "dátum") or util.today_local().isoformat())
    with db.tx():
        db.run("UPDATE invoices SET paid_at=? WHERE id=?", (paid, iid))
        db.log_history(u["id"], "invoice_paid", {"invoice_id": iid, "paid_at": paid}, _ip(request))
    return _invoice_out(db.row(db.q1("SELECT * FROM invoices WHERE id=?", (iid,))))


# --- transactions / rules --------------------------------------------------------------

@router.get("/transactions")
def transactions_list(request: Request, status: str = "pending", limit: int = 200):
    current_user(request)
    if status not in ("pending", "assigned", "invoice", "ignored", "all"):
        status = "pending"
    limit = max(1, min(500, limit))
    sql = "SELECT * FROM transactions" + ("" if status == "all" else " WHERE status=?") + " ORDER BY date DESC, id DESC LIMIT ?"
    params = ([] if status == "all" else [status]) + [limit]
    return {"transactions": db.rows(db.q(sql, params))}


@router.post("/transactions/{tid}/assign")
async def transaction_assign(request: Request, tid: int):
    u = current_user(request)
    body = await json_body(request)
    try:
        t = bank.assign_transaction(tid, u["id"], place_id=_int(body.get("place_id"), "miesto", allow_none=True),
                                    service_id=_int(body.get("service_id"), "služba", allow_none=True),
                                    category=str(body.get("category") or ""), label=util.clean_text(body.get("label"), 120),
                                    remember=bool(body.get("remember", True)), ignore=bool(body.get("ignore", False)))
    except ValueError as exc:
        raise ApiError(str(exc)) from None
    return t


@router.get("/rules")
def rules_list(request: Request):
    current_user(request)
    return {"rules": db.rows(db.q("SELECT r.*, p.name place_name, s.kind service_kind FROM rules r LEFT JOIN places p ON p.id=r.place_id "
                                  "LEFT JOIN services s ON s.id=r.service_id ORDER BY r.id DESC"))}


@router.delete("/rules/{rid}")
def rule_delete(request: Request, rid: int):
    u = current_user(request)
    with db.tx():
        db.run("DELETE FROM rules WHERE id=?", (rid,))
        db.log_history(u["id"], "rule_deleted", {"rule_id": rid}, _ip(request))
    return {"ok": True}


# --- costs -----------------------------------------------------------------------------

@router.get("/costs")
def costs_list(request: Request, month: str = "", place_id: int = 0, limit: int = 300):
    current_user(request)
    where, params = [], []
    if re.match(r"^\d{4}-\d{2}$", month or ""):
        where.append("substr(c.date,1,7)=?"); params.append(month)
    if place_id:
        where.append("c.place_id=?"); params.append(place_id)
    sql = ("WHERE " + " AND ".join(where) if where else "") + " ORDER BY c.date DESC, c.id DESC LIMIT ?"
    params.append(max(1, min(1000, limit)))
    return {"costs": _costs_rows(sql, params)}


@router.post("/costs")
async def cost_create(request: Request):
    u = current_user(request)
    b = await json_body(request)
    place_id = _int(b.get("place_id"), "miesto")
    if not db.q1("SELECT 1 FROM places WHERE id=?", (place_id,)):
        raise ApiError("Miesto neexistuje.")
    service_id = _int(b.get("service_id"), "služba", allow_none=True)
    amount = _money(b.get("amount"), "suma", allow_none=False)
    category = util.clean_text(b.get("category"), 40) or "ine"
    with db.tx():
        cid = db.run("INSERT INTO costs(place_id,service_id,kind,category,counterparty,amount,currency,date,period_from,period_to,note,created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (place_id, service_id, "rucne", category, util.clean_text(b.get("counterparty"), 120), amount, "EUR",
                      _date(b.get("date"), "dátum") or util.today_local().isoformat(), _date(b.get("period_from"), "od"),
                      _date(b.get("period_to"), "do"), util.clean_text(b.get("note"), 300, multiline=True), db.now_iso()))
        db.log_history(u["id"], "cost_created", {"cost_id": cid, "amount": amount}, _ip(request))
    return _costs_rows("WHERE c.id=?", (cid,))[0]


@router.delete("/costs/{cid}")
def cost_delete(request: Request, cid: int):
    u = current_user(request)
    c = db.row(db.q1("SELECT * FROM costs WHERE id=?", (cid,)))
    if not c:
        raise ApiError("Výdavok neexistuje.", 404)
    with db.tx():
        if c["transaction_id"]:
            db.run("UPDATE transactions SET status='pending', cost_id=NULL, rule_id=NULL WHERE id=?", (c["transaction_id"],))
        db.run("DELETE FROM costs WHERE id=?", (cid,))
        db.log_history(u["id"], "cost_deleted", {"cost_id": cid}, _ip(request))
    return {"ok": True}


# --- settings -----------------------------------------------------------------------------

def _validate_setting(key: str, val: str) -> str:
    val = util.clean_text(val, 300)
    if key in ("smtp_port", "imap_port"):
        n = _int(val or "0", key, 1, 65535)
        return str(n)
    if key in ("smtp_host", "imap_host"):
        if val and not HOST_RE.match(val):
            raise ApiError(f"{key}: neplatný názov servera.")
    if key == "ntfy_server":
        if not val.startswith("https://") or len(val) > 200:
            raise ApiError("ntfy server musí byť https:// adresa.")
        host = val[8:].split("/")[0].split(":")[0]
        try:
            if ipaddress.ip_address(host).is_private or ipaddress.ip_address(host).is_link_local:
                raise ApiError("ntfy server nesmie byť privátna adresa.")
        except ValueError:
            pass
    if key in ("imap_enabled", "zsd_enabled"):
        if val not in ("0", "1"):
            raise ApiError(f"{key}: 0 alebo 1.")
    if key == "zsd_time" and not TIME_RE.match(val):
        raise ApiError("Čas musí byť HH:MM.")
    if key == "claude_model" and not MODEL_RE.match(val):
        raise ApiError("Neplatný názov modelu.")
    if key == "smtp_from" and val and not EMAIL_RE.match(val):
        raise ApiError("Odosielateľ musí byť e-mailová adresa.")
    if key == "statement_reminder_days":
        return str(_int(val or "0", key, 0, 365))
    if key == "zsd_business_partner_id" and val and not re.match(r"^[A-Za-z0-9_-]{1,40}$", val):
        raise ApiError("Business partner ID: len písmená a číslice.")
    if key == "imap_folder" and val and not re.match(r"^[A-Za-z0-9 ._/-]{1,80}$", val):
        raise ApiError("Neplatný názov priečinka.")
    return val


@router.get("/settings")
def settings_get(request: Request):
    admin_user(request)
    return {"settings": settings.public_view(),
            "status": {"imap_last_ok": db.get_setting("imap_last_ok"), "imap_last_error": db.get_setting("imap_last_error"),
                       "zsd_last_ok": db.get_setting("zsd_last_ok"), "zsd_last_run": zsd.last_run(),
                       "zsd_delivery_points": zsd.delivery_points(), "last_statement_at": db.get_setting("last_statement_at"),
                       "mailbox_configured": mailbox.is_configured(), "zsd_configured": zsd.is_configured(),
                       "claude_configured": bool(settings.get("anthropic_api_key"))}}


@router.put("/settings")
async def settings_put(request: Request):
    u = admin_user(request)
    body = await json_body(request)
    changed = []
    with db.tx():
        for key in body.get("_clear", []) or []:
            if key in settings.SECRET_KEYS:
                settings.set_(key, ""); changed.append(key)
        for key, val in body.items():
            if key not in settings.OVERRIDABLE:
                continue
            val = "" if val is None else str(val)
            if key in settings.SECRET_KEYS:
                if not val:
                    continue
                settings.set_(key, util.clean_text(val, 300)); changed.append(key)
                continue
            settings.set_(key, _validate_setting(key, val)); changed.append(key)
        db.log_history(u["id"], "settings_updated", {"keys": changed}, _ip(request))
    return {"ok": True, "settings": settings.public_view()}


@router.post("/settings/test")
async def settings_test(request: Request):
    u = admin_user(request)
    what = (await json_body(request)).get("what")
    try:
        if what == "smtp":
            if not u.get("email"):
                raise ApiError("Najprv si v Profile vyplň e-mail.")
            mailer.send(u["email"], "Skúšobný e-mail", mailer.wrap("<p>Toto je skúšobný e-mail z Nakladiaku. Funguje.</p>"),
                        "Toto je skúšobný e-mail z Nakladiaku. Funguje.")
            return {"ok": True, "message": f"Odoslané na {u['email']}."}
        if what == "ntfy":
            topic = (await request.json()).get("topic") or u.get("ntfy_topic") or settings.get("alert_ntfy_topic")
            if not topic:
                raise ApiError("Nie je nastavená žiadna ntfy téma.")
            ntfy.push(util.clean_text(topic, 80), "Nakladiak: skúšobná notifikácia", "Funguje.", tags=["white_check_mark"])
            return {"ok": True, "message": f"Poslané na tému {topic}."}
        if what == "imap":
            return {"ok": True, "message": mailbox.test_connection()}
        if what == "claude":
            return {"ok": True, "message": extract.test_connection()}
        raise ApiError("Neznámy test.")
    except ApiError:
        raise
    except extract.ExtractError as exc:
        raise ApiError(str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        msg = re.sub(r"(?i)(password|heslo)[^ ]*", "***", str(exc))[:300]
        raise ApiError(f"Nepodarilo sa: {msg}") from None


@router.post("/mailbox/poll")
def mailbox_poll(request: Request):
    u = admin_user(request)
    if not mailbox.is_configured():
        raise ApiError("Schránka nie je nastavená.")
    db.log_history(u["id"], "mailbox_poll", {}, _ip(request))
    res = mailbox.poll_safe()
    if res is None:
        raise ApiError("Schránku sa nepodarilo prečítať: " + (db.get_setting("imap_last_error") or "")[:200])
    threading.Thread(target=_drain_bg, daemon=True).start()
    return {"ok": True, "result": res,
            "message": f"Správ: {res['messages']}, nových dokumentov: {res['stored']}, duplicít: {res['duplicates']}."}


def _drain_bg() -> None:
    try:
        for _ in range(20):
            if not documents.process_next():
                break
    finally:
        db.close()


@router.post("/connectors/{name}/run")
async def connector_run(request: Request, name: str):
    u = admin_user(request)
    if name != zsd.NAME:
        raise ApiError("Neznámy konektor.", 404)
    if not zsd.is_configured():
        raise ApiError("ZSD nie je nastavené.")
    body = await json_body(request)
    days = _int(body.get("days", 8), "dni", 1, 400)
    db.log_history(u["id"], "connector_run", {"connector": name, "days": days}, _ip(request))
    from .. import scheduler

    def work():
        try:
            scheduler.run_zsd(force=True, days=days)
        except Exception:  # noqa: BLE001
            log.exception("manual zsd run failed")
        finally:
            db.close()
    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "message": "Sťahovanie beží na pozadí (1–3 minúty). Stav v Nastaveniach → Zdroje dát."}


@router.get("/connectors/status")
def connectors_status(request: Request):
    current_user(request)
    return {"zsd": {"configured": zsd.is_configured(), "last_run": zsd.last_run(), "last_ok": db.get_setting("zsd_last_ok"),
                    "delivery_points": zsd.delivery_points(), "mapped": len(zsd.mapped_services())},
            "imap": {"configured": mailbox.is_configured(), "last_ok": db.get_setting("imap_last_ok"), "last_error": db.get_setting("imap_last_error")},
            "runs": db.rows(db.q("SELECT * FROM connector_runs ORDER BY id DESC LIMIT 20"))}


# --- profile / users ----------------------------------------------------------------------

@router.get("/profile")
def profile_get(request: Request):
    u = current_user(request)
    return public_user(u) | {"ntfy_topic": u.get("ntfy_topic", ""), "notify_ntfy": bool(u.get("notify_ntfy", 1)),
                             "notify_email": bool(u.get("notify_email", 0)), "ntfy_server": settings.get("ntfy_server")}


@router.put("/profile")
async def profile_put(request: Request):
    u = current_user(request)
    b = await json_body(request)
    name = util.clean_text(b.get("name", u["name"]), 60) or u["name"]
    email = util.clean_text(b.get("email", u["email"]), 120)
    if email and not EMAIL_RE.match(email):
        raise ApiError("Neplatný e-mail.")
    topic = util.clean_text(b.get("ntfy_topic", u.get("ntfy_topic", "")), 80)
    if topic and not re.match(r"^[A-Za-z0-9_-]{1,64}$", topic):
        raise ApiError("ntfy téma: len písmená, číslice, - a _.")
    with db.tx():
        db.run("UPDATE users SET name=?, email=?, ntfy_topic=?, notify_ntfy=?, notify_email=?, seen_changelog=? WHERE id=?",
               (name, email, topic, 1 if b.get("notify_ntfy", u.get("notify_ntfy", 1)) else 0,
                1 if b.get("notify_email", u.get("notify_email", 0)) else 0,
                _latest_changelog_date() if b.get("seen_changelog") else u.get("seen_changelog", ""), u["id"]))
        db.log_history(u["id"], "profile_updated", {}, _ip(request))
    return profile_get_fresh(u["id"])


def profile_get_fresh(uid: int) -> dict:
    u = db.row(db.q1("SELECT * FROM users WHERE id=?", (uid,)))
    return public_user(u) | {"ntfy_topic": u.get("ntfy_topic", ""), "notify_ntfy": bool(u.get("notify_ntfy", 1)),
                             "notify_email": bool(u.get("notify_email", 0)), "ntfy_server": settings.get("ntfy_server")}


@router.post("/profile/password")
async def profile_password(request: Request):
    u = current_user(request)
    b = await json_body(request)
    if not auth.verify_password(str(b.get("current") or ""), u["password_hash"]):
        raise ApiError("Súčasné heslo nesedí.")
    new = str(b.get("new") or "")
    if len(new) < 8:
        raise ApiError("Nové heslo musí mať aspoň 8 znakov.")
    auth.set_password(u["id"], new)
    db.log_history(u["id"], "password_changed", {}, _ip(request))
    fresh = db.row(db.q1("SELECT * FROM users WHERE id=?", (u["id"],)))
    from fastapi.responses import JSONResponse
    resp = JSONResponse({"ok": True})
    auth.set_cookie(resp, fresh)
    return resp


@router.post("/profile/logout-all")
def profile_logout_all(request: Request):
    u = current_user(request)
    with db.tx():
        db.run("UPDATE users SET session_version=session_version+1 WHERE id=?", (u["id"],))
        db.log_history(u["id"], "logout_everywhere", {}, _ip(request))
    fresh = db.row(db.q1("SELECT * FROM users WHERE id=?", (u["id"],)))
    from fastapi.responses import JSONResponse
    resp = JSONResponse({"ok": True})
    auth.set_cookie(resp, fresh)
    return resp


@router.get("/users")
def users_list(request: Request):
    admin_user(request)
    return {"users": [public_user(x) for x in db.rows(db.q("SELECT * FROM users ORDER BY id"))]}


def _send_invite(admin: dict, user: dict) -> tuple[bool, str]:
    url = f"{config.app_url()}/p/{auth.password_token(user, 'invite')}"
    if not user["email"] or not mailer.is_configured():
        return False, url
    host = config.app_url().split("//", 1)[-1]
    body = (f"<p>Ahoj {mailer.esc(user['name'])},</p><p>{mailer.esc(admin['name'])} ti vytvoril(a) prístup do appky Nakladiak na {mailer.esc(host)} "
            f"(náklady domácností). Prihlasovacie meno: <b>{mailer.esc(user['username'])}</b>.</p>"
            f"<p>Odkaz platí 7 dní. Ak vyprší, požiadaj {mailer.esc(admin['name'])} o nový.</p>")
    try:
        mailer.send(user["email"], f"Prístup do {host}", mailer.wrap(body, [("Nastaviť heslo", url)]),
                    f"Prihlasovacie meno: {user['username']}\nNastaviť heslo: {url}\nOdkaz platí 7 dní.")
        db.log_history(admin["id"], "invite_sent", {"user_id": user["id"]})
        return True, url
    except Exception as exc:  # noqa: BLE001
        db.log_history(None, "mail_failed", {"to": user["email"], "subject": "invite", "error": str(exc)[:200]})
        return False, url


@router.post("/users")
async def user_create(request: Request):
    admin = admin_user(request)
    b = await json_body(request)
    username = str(b.get("username") or "").strip().lower()
    if not USERNAME_RE.match(username):
        raise ApiError("Prihlasovacie meno: 2–40 znakov, malé písmená, číslice, . _ -")
    if db.q1("SELECT 1 FROM users WHERE username=?", (username,)):
        raise ApiError("Také prihlasovacie meno už existuje.")
    name = util.clean_text(b.get("name"), 60) or username.capitalize()
    email = util.clean_text(b.get("email"), 120)
    if email and not EMAIL_RE.match(email):
        raise ApiError("Neplatný e-mail.")
    mode = b.get("mode", "invite")
    is_admin = 1 if b.get("is_admin") else 0
    password_hash, must_change = "", 0
    if mode == "password":
        pw = str(b.get("password") or "")
        if len(pw) < 8:
            raise ApiError("Heslo musí mať aspoň 8 znakov.")
        password_hash = auth.hash_password(pw)
        must_change = 1 if b.get("must_change_password", True) else 0
    elif not email:
        raise ApiError("Pri pozvánke odkazom je e-mail povinný (alebo zvoľ „Nastaviť heslo hneď“).")
    with db.tx():
        uid = db.run("INSERT INTO users(username,name,email,password_hash,is_admin,must_change_password,created_at) VALUES(?,?,?,?,?,?,?)",
                     (username, name, email, password_hash, is_admin, must_change, db.now_iso()))
        db.log_history(admin["id"], "user_created", {"user_id": uid, "mode": mode, "is_admin": is_admin}, _ip(request))
    user = db.row(db.q1("SELECT * FROM users WHERE id=?", (uid,)))
    out = {"user": public_user(user), "mail_sent": False}
    if mode == "invite":
        sent, url = _send_invite(admin, user)
        out["mail_sent"], out["invite_url"] = sent, url
    return out


@router.put("/users/{uid}")
async def user_update(request: Request, uid: int):
    admin = admin_user(request)
    user = db.row(db.q1("SELECT * FROM users WHERE id=?", (uid,)))
    if not user:
        raise ApiError("Používateľ neexistuje.", 404)
    b = await json_body(request)
    name = util.clean_text(b.get("name", user["name"]), 60) or user["name"]
    email = util.clean_text(b.get("email", user["email"]), 120)
    if email and not EMAIL_RE.match(email):
        raise ApiError("Neplatný e-mail.")
    is_admin = 1 if b.get("is_admin", user["is_admin"]) else 0
    active = 1 if b.get("active", user["active"]) else 0
    admins_left = db.q1("SELECT COUNT(*) c FROM users WHERE is_admin=1 AND active=1 AND id<>?", (uid,))["c"]
    if user["is_admin"] and user["active"] and (not is_admin or not active) and admins_left == 0:
        raise ApiError("Posledného administrátora nejde odobrať ani deaktivovať.")
    bump = (is_admin != user["is_admin"]) or (active != user["active"])
    with db.tx():
        db.run("UPDATE users SET name=?, email=?, is_admin=?, active=?, session_version=session_version+? WHERE id=?",
               (name, email, is_admin, active, 1 if bump else 0, uid))
        if b.get("password"):
            if len(str(b["password"])) < 8:
                raise ApiError("Heslo musí mať aspoň 8 znakov.")
            db.run("UPDATE users SET password_hash=?, must_change_password=?, session_version=session_version+1 WHERE id=?",
                   (auth.hash_password(str(b["password"])), 1 if b.get("must_change_password", True) else 0, uid))
        db.log_history(admin["id"], "user_updated", {"user_id": uid, "is_admin": is_admin, "active": active}, _ip(request))
    out = {"user": public_user(db.row(db.q1("SELECT * FROM users WHERE id=?", (uid,))))}
    if b.get("send_invite"):
        fresh = db.row(db.q1("SELECT * FROM users WHERE id=?", (uid,)))
        sent, url = _send_invite(admin, fresh)
        out["mail_sent"], out["invite_url"] = sent, url
    return out


# --- history / about ---------------------------------------------------------------------

@router.get("/history")
def history(request: Request, before: int = 0, limit: int = 50):
    admin_user(request)
    limit = max(1, min(200, limit))
    rows = db.rows(db.q("SELECT h.*, u.name user_name FROM history h LEFT JOIN users u ON u.id=h.user_id "
                        + ("WHERE h.id<? " if before else "") + "ORDER BY h.id DESC LIMIT ?",
                        ((before, limit) if before else (limit,))))
    for r in rows:
        r["label"] = ACTION_LABELS.get(r["action"], r["action"])
        try:
            r["details"] = json.loads(r["details"]) if r["details"] else {}
        except ValueError:
            r["details"] = {}
    return {"history": rows}


def _changelog() -> list[dict]:
    path = Path(__file__).resolve().parents[2] / "changelog.md"
    if not path.is_file():
        path = Path("/srv/changelog.md")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    sections = []
    for line in text.splitlines():
        if line.startswith("## "):
            head = line[3:].strip()
            m = re.match(r"^(\d{4}-\d{2}-\d{2})\s*(?:\((.*)\))?", head)
            sections.append({"date": m.group(1) if m else "", "title": (m.group(2) if m and m.group(2) else head), "items": []})
        elif line.startswith("- ") and sections:
            sections[-1]["items"].append(_md_inline(line[2:].strip()))
    return sections[:10]


def _md_inline(s: str) -> list:
    out, pos = [], 0
    for m in re.finditer(r"\*\*(.+?)\*\*", s):
        if m.start() > pos:
            out.append(s[pos:m.start()])
        out.append({"b": m.group(1)})
        pos = m.end()
    if pos < len(s):
        out.append(s[pos:])
    return out


def _latest_changelog_date() -> str:
    c = _changelog()
    return c[0]["date"] if c else ""


@router.get("/about")
def about(request: Request):
    current_user(request)
    size = config.DB_PATH.stat().st_size if config.DB_PATH.is_file() else 0
    docs_size = sum(f.stat().st_size for f in config.DOCS_DIR.rglob("*") if f.is_file()) if config.DOCS_DIR.is_dir() else 0
    return {"name": config.APP_NAME, "built_at": config.built_at(), "changes": _changelog(), "db_bytes": size, "docs_bytes": docs_size,
            "documents": db.q1("SELECT COUNT(*) c FROM documents")["c"], "model": settings.get("claude_model")}
