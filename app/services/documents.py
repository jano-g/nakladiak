"""Documents: storing uploads / mail attachments, running the extraction, turning the result
into invoices, costs and transactions, and the review step when the app is not sure.

Statuses: new → processing → done | needs_review | error (retried with backoff, then alert)."""
import hashlib
import json
import logging
import re
import threading
from datetime import timedelta
from pathlib import Path

from .. import config, db, util
from . import alerts, bank, extract, notify

log = logging.getLogger(__name__)
_process_lock = threading.Lock()

ALLOWED_MIME = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                "image/gif": ".gif"}
DOC_KINDS = ("auto", "faktura", "uctenka", "vypis", "ine")
MAX_ATTEMPTS = 4
BACKOFF_MIN = [5, 30, 180, 720]


class DocError(RuntimeError):
    pass


def sniff_mime(data: bytes, declared: str) -> str:
    if data[:5] == b"%PDF-":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return declared or ""


def store(filename: str, data: bytes, declared_mime: str, source: str, user_id=None, kind: str = "auto",
          mail_key: str | None = None, mail_from: str = "", mail_subject: str = "", hint: str = "") -> tuple[dict, bool]:
    """Saves the file and the row. Returns (document, created). A file we already have (same
    sha256) is returned with created=False and nothing is written."""
    if not data:
        raise DocError("Súbor je prázdny.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise DocError("Súbor je väčší ako 25 MB.")
    mime = sniff_mime(data, declared_mime)
    if mime not in ALLOWED_MIME:
        raise DocError("Podporované sú PDF a fotky (JPG, PNG, WEBP).")
    if kind not in DOC_KINDS:
        kind = "auto"
    sha = hashlib.sha256(data).hexdigest()
    existing = db.row(db.q1("SELECT * FROM documents WHERE sha256=?", (sha,)))
    if existing:
        return existing, False
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", util.fold(filename) or "dokument")[:60]
    if not safe.lower().endswith(ALLOWED_MIME[mime]):
        safe += ALLOWED_MIME[mime]
    now = db.now_iso()
    with db.tx():
        doc_id = db.run(
            "INSERT INTO documents(kind,status,source,filename,path,mime,size,sha256,mail_key,mail_from,mail_subject,"
            "received_at,review_note,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kind, "new", source, util.clean_text(filename, 200) or safe, "", mime, len(data), sha, mail_key,
             util.clean_text(mail_from, 200), util.clean_text(mail_subject, 200), now,
             util.clean_text(hint, 500), user_id, now, now))
        sub = config.DOCS_DIR / now[:4]
        sub.mkdir(parents=True, exist_ok=True)
        rel = f"{now[:4]}/{doc_id}-{sha[:8]}-{safe}"
        (config.DOCS_DIR / rel).write_bytes(data)
        db.run("UPDATE documents SET path=? WHERE id=?", (rel, doc_id))
    return load(doc_id), True


def file_path(doc: dict) -> Path:
    p = (config.DOCS_DIR / doc["path"]).resolve()
    if config.DOCS_DIR.resolve() not in p.parents:
        raise DocError("Neplatná cesta dokumentu.")
    return p


def load(doc_id: int) -> dict | None:
    d = db.row(db.q1("SELECT * FROM documents WHERE id=?", (doc_id,)))
    if d:
        d["data"] = json.loads(d["extracted"]) if d["extracted"] else None
    return d


def _save_extracted(doc_id: int, data: dict) -> None:
    db.run("UPDATE documents SET extracted=?, updated_at=? WHERE id=?",
           (json.dumps(data, ensure_ascii=False), db.now_iso(), doc_id))


# --- matching -------------------------------------------------------------------

def _services(active_only=True) -> list[dict]:
    sql = "SELECT * FROM services" + (" WHERE active=1" if active_only else "")
    return db.rows(db.q(sql))


def _places() -> list[dict]:
    return db.rows(db.q("SELECT * FROM places WHERE archived=0 ORDER BY sort, id"))


def match_service(data: dict, services: list[dict]) -> tuple[dict | None, str]:
    """Deterministic first (identifier printed on the bill == identifier of a service, or a rule
    learned from an earlier review), then the model's own guess when confident. Returns
    (service, how) with how in identifier | rule | model | ''."""
    idents = {util.norm_identifier(i.get("value")) for i in data.get("identifiers") or [] if i.get("value")}
    idents.discard("")
    by_id = {s["id"]: s for s in services}
    if idents:
        for s in services:
            for key in (s.get("identifier"), s.get("identifier2")):
                if key and util.norm_identifier(key) in idents:
                    return s, "identifier"
        for ident in idents:
            r = db.q1("SELECT * FROM rules WHERE match_kind='identifier' AND pattern=? AND service_id IS NOT NULL", (ident,))
            if r and r["service_id"] in by_id:
                db.run("UPDATE rules SET hits=hits+1 WHERE id=?", (r["id"],))
                return by_id[r["service_id"]], "rule"
    sup = util.fold(data.get("supplier"))
    kind = data.get("service_kind") or ""
    if sup:
        r = db.q1("SELECT * FROM rules WHERE match_kind='supplier' AND pattern=? AND service_id IS NOT NULL",
                  (f"{sup}|{kind}",))
        if r and r["service_id"] in by_id:
            db.run("UPDATE rules SET hits=hits+1 WHERE id=?", (r["id"],))
            return by_id[r["service_id"]], "rule"
        same = [s for s in services if s["kind"] == kind and sup and util.fold(s["supplier"]) and
                (util.fold(s["supplier"]) in sup or sup in util.fold(s["supplier"]))]
        if len(same) == 1:
            return same[0], "supplier"
    mid = data.get("matched_service_id")
    if mid in by_id and float(data.get("match_confidence") or 0) >= 0.8:
        return by_id[mid], "model"
    return None, ""


# --- processing -----------------------------------------------------------------

def process_next() -> bool:
    """Scheduler entry: one document per call, under a lock (Claude calls take 10–60 s)."""
    if not _process_lock.acquire(blocking=False):
        return False
    try:
        now = db.now_iso()
        d = db.q1("SELECT id FROM documents WHERE status IN ('new','error') AND attempts<? "
                  "AND (next_try_at IS NULL OR next_try_at<=?) ORDER BY id LIMIT 1", (MAX_ATTEMPTS, now))
        if not d:
            return False
        process(d["id"])
        return True
    finally:
        _process_lock.release()


def process(doc_id: int) -> dict:
    doc = load(doc_id)
    if not doc:
        raise DocError("Dokument neexistuje.")
    db.run("UPDATE documents SET status='processing', attempts=attempts+1, updated_at=? WHERE id=?", (db.now_iso(), doc_id))
    try:
        data = extract.extract(file_path(doc), doc["mime"], _places(), _services(), hint=doc.get("review_note") or "")
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)[:300] if isinstance(exc, extract.ExtractError) else "Neočakávaná chyba pri čítaní dokumentu."
        if not isinstance(exc, extract.ExtractError):
            log.exception("extract failed for document %s", doc_id)
        attempts = doc["attempts"] + 1
        wait = BACKOFF_MIN[min(attempts, len(BACKOFF_MIN)) - 1]
        nxt = (util.now_local() + timedelta(minutes=wait)).astimezone().isoformat()
        db.run("UPDATE documents SET status='error', error=?, next_try_at=?, updated_at=? WHERE id=?",
               (msg, nxt, db.now_iso(), doc_id))
        if attempts >= MAX_ATTEMPTS:
            alerts.alert(f"extract:{doc_id}", "dokument sa nedá prečítať", f"{doc['filename']}: {msg}")
            notify.broadcast("Dokument sa nepodarilo prečítať", f"{doc['filename']}: {msg}",
                             click=f"{config.app_url()}/#/documents/{doc_id}", tags=["warning"])
        return load(doc_id)
    if doc["kind"] != "auto" and data.get("doc_kind") != doc["kind"]:
        data["doc_kind_model"] = data.get("doc_kind")
        data["doc_kind"] = doc["kind"]
    with db.tx():
        _save_extracted(doc_id, data)
        apply(doc_id, data)
    doc = load(doc_id)
    _announce(doc)
    return doc


def _announce(doc: dict) -> None:
    data = doc.get("data") or {}
    summary = data.get("summary") or doc["filename"]
    url = f"{config.app_url()}/#/documents/{doc['id']}"
    if doc["status"] == "needs_review":
        notify.broadcast("Dokument čaká na tvoje potvrdenie", summary, click=url, tags=["question"])
    elif doc["status"] == "done":
        extra = ""
        if data.get("doc_kind") == "vypis":
            n = db.q1("SELECT COUNT(*) c FROM transactions WHERE document_id=? AND status='pending'", (doc["id"],))["c"]
            if n:
                extra = f" {util.plural(n, 'platba čaká', 'platby čakajú', 'platieb čaká')} na zaradenie."
        notify.broadcast("Dokument spracovaný", summary + extra, click=url, tags=["white_check_mark"])


def apply(doc_id: int, data: dict) -> None:
    """Turn the extracted JSON into rows. Runs inside the caller's transaction."""
    kind = data.get("doc_kind") or "ine"
    db.run("DELETE FROM costs WHERE document_id=?", (doc_id,))
    db.run("DELETE FROM invoices WHERE document_id=?", (doc_id,))
    status, place_id, service_id = "needs_review", None, None
    if kind == "faktura" and data.get("invoice"):
        inv = data["invoice"]
        service, how = match_service(data, _services())
        if service:
            service_id, place_id = service["id"], service["place_id"]
            status = "done"
        inv_id = _insert_invoice(doc_id, service_id, data, inv)
        if service:
            _cost_from_invoice(doc_id, inv_id, service, inv)
            _learn_from_invoice(service, data, inv)
        data["match_how"] = how
    elif kind == "uctenka" and data.get("receipt"):
        rc = data["receipt"]
        rule = bank.find_rule("merchant", util.fold(rc.get("merchant")))
        pid = rule["place_id"] if rule else (data.get("matched_place_id") if float(data.get("match_confidence") or 0) >= 0.8 else None)
        if pid and db.q1("SELECT 1 FROM places WHERE id=? AND archived=0", (pid,)):
            place_id = pid
            cat = (rule["category"] if rule else "") or rc.get("category_hint") or "nakup"
            db.run("INSERT INTO costs(place_id,service_id,document_id,kind,category,counterparty,amount,currency,date,note,created_at)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (place_id, rule["service_id"] if rule else None, doc_id, "uctenka", util.clean_text(cat, 40),
                    util.clean_text(rc.get("merchant"), 120), abs(util.to_float(rc.get("total"), 0.0)),
                    rc.get("currency") or "EUR", rc.get("date") or db.now_iso()[:10],
                    util.clean_text(data.get("summary"), 200), db.now_iso()))
            status = "done"
            if rule:
                db.run("UPDATE rules SET hits=hits+1 WHERE id=?", (rule["id"],))
    elif kind == "vypis" and data.get("statement"):
        bank.import_statement(doc_id, data["statement"])
        status = "done"
        db.set_setting("last_statement_at", db.now_iso())
    db.run("UPDATE documents SET kind=?, status=?, place_id=?, service_id=?, error='', updated_at=? WHERE id=?",
           (kind, status, place_id, service_id, db.now_iso(), doc_id))
    _save_extracted(doc_id, data)


def _insert_invoice(doc_id: int, service_id, data: dict, inv: dict) -> int:
    return db.run(
        "INSERT INTO invoices(document_id,service_id,supplier,number,kind,issued_at,period_from,period_to,due_at,total,"
        "to_pay,advances,currency,consumption,unit,unit_price,variable_symbol,iban,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (doc_id, service_id, util.clean_text(data.get("supplier"), 120), util.clean_text(inv.get("number"), 60),
         inv.get("kind") or "pravidelna", inv.get("issued_at"), inv.get("period_from"), inv.get("period_to"),
         inv.get("due_at"), util.to_float(inv.get("total"), 0.0), util.to_float(inv.get("to_pay")),
         util.to_float(inv.get("advances")), inv.get("currency") or "EUR", util.to_float(inv.get("consumption")),
         util.clean_text(inv.get("unit"), 10), util.to_float(inv.get("unit_price")),
         util.norm_identifier(inv.get("variable_symbol")), util.norm_identifier(inv.get("iban")), db.now_iso()))


def _cost_from_invoice(doc_id: int, inv_id: int, service: dict, inv: dict) -> None:
    """One cost row per invoice: the total for the period. An annual vyúčtovanie carries the
    whole year's cost minus advances already counted monthly, so for those we book only the
    balance (to_pay), never the total twice."""
    kind = inv.get("kind") or "pravidelna"
    amount = util.to_float(inv.get("total"), 0.0)
    if kind == "vyuctovanie" and inv.get("to_pay") is not None and inv.get("advances"):
        amount = util.to_float(inv.get("to_pay"), amount)
    if kind == "dobropis":
        amount = -abs(amount)
    date = inv.get("issued_at") or inv.get("period_to") or db.now_iso()[:10]
    db.run("INSERT INTO costs(place_id,service_id,document_id,invoice_id,kind,category,counterparty,amount,currency,date,"
           "period_from,period_to,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (service["place_id"], service["id"], doc_id, inv_id, "faktura", service["kind"],
            util.clean_text(service.get("supplier") or "", 120), amount, inv.get("currency") or "EUR", date,
            inv.get("period_from"), inv.get("period_to"), db.now_iso()))


def _learn_from_invoice(service: dict, data: dict, inv: dict) -> None:
    """Keep the service's price knowledge fresh so estimates use the latest tariff."""
    sets, vals = [], []
    if util.to_float(inv.get("unit_price")):
        sets.append("unit_price=?"); vals.append(util.to_float(inv.get("unit_price")))
    if util.to_float(inv.get("fixed_monthly")) is not None and util.to_float(inv.get("fixed_monthly")):
        sets.append("fixed_monthly=?"); vals.append(util.to_float(inv.get("fixed_monthly")))
    if inv.get("unit") and not service.get("unit"):
        sets.append("unit=?"); vals.append(util.clean_text(inv.get("unit"), 10))
    if data.get("supplier") and not service.get("supplier"):
        sets.append("supplier=?"); vals.append(util.clean_text(data.get("supplier"), 120))
    if (inv.get("kind") or "") == "zalohova" and util.to_float(inv.get("total")):
        sets.append("monthly_estimate=?"); vals.append(util.to_float(inv.get("total")))
    if not service.get("identifier"):
        for i in data.get("identifiers") or []:
            if i.get("kind", "").upper() in ("EIC", "POD") and i.get("value"):
                sets.append("identifier=?"); vals.append(util.clean_text(i["value"], 60)); break
    if sets:
        sets.append("updated_at=?"); vals.append(db.now_iso()); vals.append(service["id"])
        db.run(f"UPDATE services SET {', '.join(sets)} WHERE id=?", vals)


# --- review ---------------------------------------------------------------------

def review(doc_id: int, user_id: int, place_id=None, service_id=None, category: str = "", kind: str = "",
           remember: bool = True) -> dict:
    """The user tells us where the document belongs. We re-apply with that answer and, when
    asked, remember it as a rule so the next one from the same supplier/shop goes through alone."""
    doc = load(doc_id)
    if not doc or not doc.get("data"):
        raise DocError("Dokument ešte nie je prečítaný.")
    data = doc["data"]
    if kind in DOC_KINDS and kind != "auto":
        data["doc_kind"] = kind
    service = db.row(db.q1("SELECT * FROM services WHERE id=?", (service_id,))) if service_id else None
    if service:
        place_id = service["place_id"]
    if place_id and not db.q1("SELECT 1 FROM places WHERE id=?", (place_id,)):
        raise DocError("Miesto neexistuje.")
    with db.tx():
        if data.get("doc_kind") == "faktura" and data.get("invoice"):
            if not service:
                raise DocError("Vyber službu, ku ktorej faktúra patrí.")
            if remember:
                for i in data.get("identifiers") or []:
                    v = util.norm_identifier(i.get("value"))
                    if v and i.get("kind", "").upper() in ("EIC", "POD", "CISLO_ZAKAZNIKA", "CISLO_ZMLUVY", "CISLO_ODBERNEHO_MIESTA", "TELEFON"):
                        bank.upsert_rule("identifier", v, place_id=place_id, service_id=service["id"], label=data.get("supplier") or "")
                sup = util.fold(data.get("supplier"))
                if sup:
                    bank.upsert_rule("supplier", f"{sup}|{data.get('service_kind') or ''}", place_id=place_id,
                                     service_id=service["id"], label=data.get("supplier") or "")
            apply(doc_id, data)
            # match_service() runs inside apply(); force the user's choice if it still disagreed
            db.run("UPDATE documents SET status='done', place_id=?, service_id=? WHERE id=?", (place_id, service["id"], doc_id))
            inv = db.row(db.q1("SELECT * FROM invoices WHERE document_id=?", (doc_id,)))
            if inv and inv["service_id"] != service["id"]:
                db.run("UPDATE invoices SET service_id=? WHERE id=?", (service["id"], inv["id"]))
                db.run("DELETE FROM costs WHERE document_id=?", (doc_id,))
                _cost_from_invoice(doc_id, inv["id"], service, data["invoice"])
                _learn_from_invoice(service, data, data["invoice"])
        elif data.get("doc_kind") == "uctenka" and data.get("receipt"):
            if not place_id:
                raise DocError("Vyber miesto, ku ktorému účtenka patrí.")
            rc = data["receipt"]
            cat = util.clean_text(category, 40) or rc.get("category_hint") or "nakup"
            if remember and util.fold(rc.get("merchant")):
                bank.upsert_rule("merchant", util.fold(rc.get("merchant")), place_id=place_id,
                                 service_id=service["id"] if service else None, category=cat, label=rc.get("merchant") or "")
            db.run("DELETE FROM costs WHERE document_id=?", (doc_id,))
            db.run("INSERT INTO costs(place_id,service_id,document_id,kind,category,counterparty,amount,currency,date,note,created_at)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (place_id, service["id"] if service else None, doc_id, "uctenka", cat,
                    util.clean_text(rc.get("merchant"), 120), abs(util.to_float(rc.get("total"), 0.0)),
                    rc.get("currency") or "EUR", rc.get("date") or db.now_iso()[:10],
                    util.clean_text(data.get("summary"), 200), db.now_iso()))
            db.run("UPDATE documents SET kind='uctenka', status='done', place_id=?, service_id=?, updated_at=? WHERE id=?",
                   (place_id, service["id"] if service else None, db.now_iso(), doc_id))
        elif data.get("doc_kind") == "vypis" and data.get("statement"):
            apply(doc_id, data)
        else:
            # "iné": keep the file, attach it to a place, no cost row
            db.run("UPDATE documents SET kind='ine', status='done', place_id=?, updated_at=? WHERE id=?",
                   (place_id, db.now_iso(), doc_id))
        _save_extracted(doc_id, data)
        db.log_history(user_id, "document_reviewed", {"document_id": doc_id, "place_id": place_id, "service_id": service_id})
    return load(doc_id)


def reprocess(doc_id: int, hint: str = "") -> None:
    with db.tx():
        db.run("UPDATE documents SET status='new', attempts=0, next_try_at=NULL, error='', review_note=?, updated_at=? WHERE id=?",
               (util.clean_text(hint, 500), db.now_iso(), doc_id))


def delete(doc_id: int) -> None:
    doc = load(doc_id)
    if not doc:
        return
    with db.tx():
        db.run("DELETE FROM transactions WHERE document_id=?", (doc_id,))
        db.run("DELETE FROM costs WHERE document_id=?", (doc_id,))
        db.run("DELETE FROM invoices WHERE document_id=?", (doc_id,))
        db.run("DELETE FROM documents WHERE id=?", (doc_id,))
    try:
        file_path(doc).unlink(missing_ok=True)
    except (OSError, DocError):
        pass
