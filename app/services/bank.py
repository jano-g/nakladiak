"""Bank statements: transactions, matching them to invoices (paid!) or to learned rules
(gardener, caretaker, cleaning → place + category), and the "Na zaradenie" queue."""
import hashlib
import logging

from .. import db, util

log = logging.getLogger(__name__)

CATEGORIES = ["elektrina", "plyn", "voda", "internet", "tv", "mobil", "odpad", "kurenie", "poistenie", "najom",
              "udrzba", "zahrada", "upratovanie", "spravca", "dane", "nakup", "ine"]


def find_rule(match_kind: str, pattern: str) -> dict | None:
    if not pattern:
        return None
    return db.row(db.q1("SELECT * FROM rules WHERE match_kind=? AND pattern=?", (match_kind, pattern)))


def upsert_rule(match_kind: str, pattern: str, *, place_id=None, service_id=None, category: str = "",
                label: str = "", action: str = "assign") -> int:
    pattern = str(pattern or "").strip()[:200]
    if not pattern:
        return 0
    r = find_rule(match_kind, pattern)
    if r:
        db.run("UPDATE rules SET place_id=?, service_id=?, category=?, label=?, action=? WHERE id=?",
               (place_id, service_id, category, util.clean_text(label, 120), action, r["id"]))
        return r["id"]
    return db.run("INSERT INTO rules(match_kind,pattern,action,place_id,service_id,category,label,created_at) VALUES(?,?,?,?,?,?,?,?)",
                  (match_kind, pattern, action, place_id, service_id, category, util.clean_text(label, 120), db.now_iso()))


def _fingerprint(t: dict) -> str:
    raw = "|".join(str(t.get(k) or "").strip() for k in ("date", "amount", "counterparty", "counterparty_iban", "variable_symbol", "note"))
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def import_statement(doc_id: int, st: dict) -> dict:
    """Insert transactions (idempotent by fingerprint) and classify each one. Returns counts."""
    counts = {"new": 0, "duplicate": 0, "invoice": 0, "assigned": 0, "pending": 0, "ignored": 0}
    for t in st.get("transactions") or []:
        amount = util.to_float(t.get("amount"))
        date = (t.get("date") or "")[:10]
        if amount is None or abs(amount) > 1_000_000 or not util.parse_date(date):
            continue
        fp = _fingerprint(t)
        if db.q1("SELECT 1 FROM transactions WHERE fingerprint=?", (fp,)):
            counts["duplicate"] += 1
            continue
        tid = db.run("INSERT INTO transactions(document_id,date,amount,currency,counterparty,counterparty_iban,variable_symbol,"
                     "note,fingerprint,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                     (doc_id, date, round(amount, 2), (str(t.get("currency") or "EUR").upper()[:3] or "EUR"), util.clean_text(t.get("counterparty"), 120),
                      util.norm_identifier(t.get("counterparty_iban"))[:34], util.norm_identifier(t.get("variable_symbol"))[:40],
                      util.clean_text(t.get("note"), 200), fp, "pending", db.now_iso()))
        counts["new"] += 1
        counts[classify(tid)] += 1
    return counts


def classify(tid: int) -> str:
    """invoice (paid a known bill) | assigned (rule) | ignored (credit) | pending (ask the user)."""
    t = db.row(db.q1("SELECT * FROM transactions WHERE id=?", (tid,)))
    if t["amount"] > 0:
        db.run("UPDATE transactions SET status='ignored' WHERE id=?", (tid,))
        return "ignored"
    inv = _match_invoice(t)
    if inv:
        db.run("UPDATE transactions SET status='invoice', invoice_id=? WHERE id=?", (inv["id"], tid))
        db.run("UPDATE invoices SET paid_at=?, paid_transaction_id=? WHERE id=?", (t["date"], tid, inv["id"]))
        return "invoice"
    rule = None
    if t["counterparty_iban"]:
        rule = find_rule("iban", t["counterparty_iban"])
    if not rule and t["counterparty"]:
        rule = find_rule("counterparty", util.fold(t["counterparty"]))
    if rule:
        if rule["action"] == "ignore":
            db.run("UPDATE transactions SET status='ignored', rule_id=? WHERE id=?", (rule["id"], tid))
            db.run("UPDATE rules SET hits=hits+1 WHERE id=?", (rule["id"],))
            return "ignored"
        if rule["service_id"] and _service_has_invoice_near(rule["service_id"], t):
            # a utility we already count through its invoice: the transfer is the payment, not a second cost
            db.run("UPDATE transactions SET status='invoice', rule_id=? WHERE id=?", (rule["id"], tid))
            return "invoice"
        _assign(t, rule["place_id"], rule["service_id"], rule["category"], rule["id"])
        db.run("UPDATE rules SET hits=hits+1 WHERE id=?", (rule["id"],))
        return "assigned"
    return "pending"


def _match_invoice(t: dict) -> dict | None:
    amt = abs(t["amount"])
    if t["variable_symbol"]:
        inv = db.q1("SELECT * FROM invoices WHERE paid_at IS NULL AND variable_symbol=? AND variable_symbol<>'' "
                    "AND ABS(COALESCE(to_pay,total)-?)<0.05 ORDER BY id DESC", (t["variable_symbol"], amt))
        if inv:
            return db.row(inv)
    if t["counterparty_iban"]:
        inv = db.q1("SELECT * FROM invoices WHERE paid_at IS NULL AND iban=? AND iban<>'' AND ABS(COALESCE(to_pay,total)-?)<0.05 "
                    "AND ABS(julianday(COALESCE(due_at,issued_at,?))-julianday(?))<=45 ORDER BY id DESC",
                    (t["counterparty_iban"], amt, t["date"], t["date"]))
        if inv:
            return db.row(inv)
    return None


def _service_has_invoice_near(service_id: int, t: dict) -> bool:
    """A regular bill (monthly / quarterly / half-year) within ±45 days: the transfer pays it.
    A vyúčtovanie or a zálohový predpis does not count — the advances paid around them are
    costs of their own (the vyúčtovanie books only its balance)."""
    return bool(db.q1("SELECT 1 FROM invoices WHERE service_id=? AND kind IN ('pravidelna','ine','dobropis') "
                      "AND ABS(julianday(COALESCE(issued_at,period_to,?))-julianday(?))<=45",
                      (service_id, t["date"], t["date"])))


def _assign(t: dict, place_id, service_id, category: str, rule_id=None) -> int:
    if service_id:
        from . import documents
        same = documents.advance_cost_near(service_id, t["date"], abs(t["amount"]))
        if same and same["kind"] == "zaloha" and not same["transaction_id"]:
            # the vyúčtovanie already listed this advance: the transfer is that row, not a second one
            db.run("UPDATE costs SET transaction_id=?, counterparty=? WHERE id=?", (t["id"], t["counterparty"], same["id"]))
            db.run("UPDATE transactions SET status='assigned', cost_id=?, rule_id=? WHERE id=?", (same["id"], rule_id, t["id"]))
            return same["id"]
    cost_id = db.run("INSERT INTO costs(place_id,service_id,document_id,transaction_id,kind,category,counterparty,amount,currency,date,note,created_at)"
                     " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (place_id, service_id, t["document_id"], t["id"], "prevod", category or "ine", t["counterparty"],
                      abs(t["amount"]), t["currency"], t["date"], t["note"], db.now_iso()))
    db.run("UPDATE transactions SET status='assigned', cost_id=?, rule_id=? WHERE id=?", (cost_id, rule_id, t["id"]))
    return cost_id


def assign_transaction(tid: int, user_id: int, place_id=None, service_id=None, category: str = "", label: str = "",
                       remember: bool = True, ignore: bool = False) -> dict:
    t = db.row(db.q1("SELECT * FROM transactions WHERE id=?", (tid,)))
    if not t:
        raise ValueError("Platba neexistuje.")
    category = util.clean_text(category, 40)
    if place_id and not db.q1("SELECT 1 FROM places WHERE id=?", (place_id,)):
        raise ValueError("Miesto neexistuje.")
    if service_id:
        s = db.q1("SELECT place_id FROM services WHERE id=?", (service_id,))
        if not s:
            raise ValueError("Služba neexistuje.")
        if place_id and s["place_id"] != place_id:
            raise ValueError("Služba nepatrí k vybranému miestu.")
        place_id = place_id or s["place_id"]
    with db.tx():
        if t["cost_id"]:
            # a row the vyúčtovanie listed stays the invoice's; only our own transfer row goes
            db.run("UPDATE costs SET transaction_id=NULL WHERE id=? AND kind='zaloha'", (t["cost_id"],))
            db.run("DELETE FROM costs WHERE id=? AND kind<>'zaloha'", (t["cost_id"],))
            db.run("UPDATE transactions SET cost_id=NULL WHERE id=?", (tid,))
        rule_id = None
        if remember and (t["counterparty_iban"] or t["counterparty"]):
            kind, pat = ("iban", t["counterparty_iban"]) if t["counterparty_iban"] else ("counterparty", util.fold(t["counterparty"]))
            rule_id = upsert_rule(kind, pat, place_id=place_id, service_id=service_id, category=category,
                                  label=label or t["counterparty"], action="ignore" if ignore else "assign")
        if ignore:
            db.run("UPDATE transactions SET status='ignored', rule_id=? WHERE id=?", (rule_id, tid))
        else:
            if not place_id:
                raise ValueError("Vyber miesto.")
            _assign(t, place_id, service_id, category or "ine", rule_id)
        db.log_history(user_id, "transaction_assigned", {"transaction_id": tid, "place_id": place_id, "category": category, "ignore": ignore})
    return db.row(db.q1("SELECT * FROM transactions WHERE id=?", (tid,)))


def pending(limit: int = 200) -> list[dict]:
    return db.rows(db.q("SELECT * FROM transactions WHERE status='pending' ORDER BY date DESC, id DESC LIMIT ?", (limit,)))
