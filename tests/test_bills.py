"""The shapes of Jano's real bills (2026-10-27): Starlink monthly in English, UPC for half a year,
two ZSE annual settlements for the flat (nedoplatok and preplatok), the ZSE bundle for the house
(consumption + PV feed-in + summary, 11 listed advances, new advance schedule). Numbers are
structurally real, identifiers made up. Rule under test: no euro is counted twice."""
from app import db
from app.services import bank, documents, extract

from conftest import BASE, PDF, invoice_result, make_place, make_service


def _process(monkeypatch, result: dict, name: str, source: str = "upload") -> dict:
    monkeypatch.setattr(extract, "extract", lambda *a, **k: __import__("json").loads(__import__("json").dumps(result)))
    doc, created = documents.store(name, PDF + name.encode(), "application/pdf", source)
    assert created, name
    return documents.process(doc["id"])


def _costs(doc_id: int) -> list[dict]:
    return db.rows(db.q("SELECT * FROM costs WHERE document_id=? ORDER BY date, id", (doc_id,)))


def _service(sid: int) -> dict:
    return db.row(db.q1("SELECT * FROM services WHERE id=?", (sid,)))


def _statement(transactions: list[dict], period_to="2026-10-31") -> dict:
    return BASE | {"doc_kind": "vypis", "summary": "Výpis", "statement": {
        "account_iban": "SK89", "period_from": "2026-01-01", "period_to": period_to, "transactions": transactions}}


def test_half_year_internet_bill_is_spread_over_its_months_and_never_estimated_on_top(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "internet", supplier="UPC", identifier="8806664")
    res = invoice_result(supplier="UPC", service_kind="internet",
                         identifiers=[{"kind": "variabilny_symbol", "value": "8806664"}],
                         invoice={"number": "223254202", "kind": "pravidelna", "issued_at": "2026-10-01",
                                  "period_from": "2026-10-01", "period_to": "2027-03-31", "due_at": "2026-10-15",
                                  "total": 89.70, "to_pay": 89.70, "consumption": None, "unit": None, "unit_price": None,
                                  "fixed_monthly": 14.95, "variable_symbol": "8806664", "iban": "SK4411000000002625530334"})
    d = _process(monkeypatch, res, "upc.pdf")
    assert d["status"] == "done" and d["service_id"] == s["id"]
    rows = _costs(d["id"])
    assert [r["date"] for r in rows] == ["2026-10-01", "2026-11-01", "2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01"]
    assert round(sum(r["amount"] for r in rows), 2) == 89.70 and rows[0]["amount"] == 14.95
    assert _service(s["id"])["monthly_estimate"] == 14.95
    dec = next(x for pl in jano.get("/api/dashboard?month=2026-12").json()["places"] for x in pl["services"])
    assert dec["source"] == "faktura" and dec["amount"] == 14.95
    apr = next(x for pl in jano.get("/api/dashboard?month=2027-04").json()["places"] for x in pl["services"])
    assert apr["source"] == "odhad" and apr["amount"] == 14.95
    # the transfer for the whole bill pays it — it is not a seventh cost
    monkeypatch.setattr(extract, "extract", lambda *a, **k: _statement([
        {"date": "2026-10-13", "amount": -89.70, "currency": "EUR", "counterparty": "UPC BROADBAND SLOVAKIA",
         "counterparty_iban": "SK4411000000002625530334", "variable_symbol": "8806664", "note": ""}]))
    doc, _ = documents.store("vypis-upc.pdf", PDF + b"upc-st", "application/pdf", "upload")
    documents.process(doc["id"])
    assert db.q1("SELECT status FROM transactions")["status"] == "invoice"
    assert db.q1("SELECT paid_at FROM invoices WHERE document_id=?", (d["id"],))["paid_at"] == "2026-10-13"
    assert db.q1("SELECT COUNT(*) c FROM costs")["c"] == 6


def test_monthly_starlink_bill_in_english_is_one_row(jano, monkeypatch):
    p = make_place(jano, "Dom v Belej", "dom")
    s = make_service(jano, p["id"], "internet", supplier="Starlink", identifier="KIT300099552")
    res = invoice_result(supplier="Starlink", service_kind="internet",
                         identifiers=[{"kind": "cislo_zakaznika", "value": "ACC-1450775-64461-15"}, {"kind": "zariadenie", "value": "KIT300099552"}],
                         invoice={"number": "INV-DF-SVK-149965-48432-82", "kind": "pravidelna", "issued_at": "2025-09-27",
                                  "period_from": "2025-09-27", "period_to": "2025-10-27", "due_at": "2025-09-27", "total": 50.0,
                                  "to_pay": 50.0, "consumption": None, "unit": None, "unit_price": None, "fixed_monthly": 50.0,
                                  "variable_symbol": None, "iban": None})
    d = _process(monkeypatch, res, "starlink.pdf")
    assert d["status"] == "done" and d["data"]["match_how"] == "identifier"
    rows = _costs(d["id"])
    assert len(rows) == 1 and rows[0]["amount"] == 50.0 and rows[0]["date"] == "2025-09-27"
    assert _service(s["id"])["monthly_estimate"] == 50.0


def test_overpaid_settlement_books_a_negative_balance_and_is_not_due(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE", identifier="24ZZS5015210000K")
    res = invoice_result(supplier="ZSE", identifiers=[{"kind": "EIC", "value": "24ZZS5015210000K"}, {"kind": "cislo_zakaznika", "value": "5100531776"}],
                         invoice={"number": "7181636138", "kind": "vyuctovanie", "issued_at": "2026-08-16", "period_from": "2025-08-14",
                                  "period_to": "2026-08-11", "due_at": "2026-08-31", "total": 501.94, "to_pay": -118.03, "advances": 620.0,
                                  "consumption": 2494, "unit": "kWh", "unit_price": 0.13, "fixed_monthly": 7.2, "variable_symbol": "6310871487",
                                  "next_advance": {"amount": 142.0, "per_months": 3, "first_due": "2026-10-02"},
                                  "advance_payments": [{"date": "2025-10-02", "amount": 155.0}, {"date": "2025-12-02", "amount": 155.0},
                                                       {"date": "2026-03-02", "amount": 155.0}, {"date": "2026-06-05", "amount": 155.0}]})
    d = _process(monkeypatch, res, "zse-byt2.pdf")
    assert d["status"] == "done"
    rows = _costs(d["id"])
    balance = [r for r in rows if r["kind"] == "faktura"]
    assert len(balance) == 1 and balance[0]["amount"] == -118.03 and balance[0]["date"] == "2026-08-16"
    assert [r["amount"] for r in rows if r["kind"] == "zaloha"] == [155.0] * 4
    assert round(sum(r["amount"] for r in rows), 2) == 501.97  # = total + úrok z omeškania 0,03 on the bill
    svc = _service(s["id"])
    assert svc["monthly_estimate"] == 47.33 and svc["identifier2"] == "6310871487"
    assert jano.get("/api/dashboard?month=2026-08").json()["due"] == []
    inv = jano.get(f"/api/documents/{d['id']}").json()["invoice"]
    assert inv["advance_amount"] == 142.0 and inv["advance_months"] == 3 and inv["advance_from"] == "2026-10-02"


def test_house_bundle_books_balance_feed_in_and_listed_advances_once(jano, monkeypatch):
    p = make_place(jano, "Dom v Belej", "dom")
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE", identifier="24ZZS7001255000R")
    advances = [{"date": f"2025-{m:02d}-15", "amount": 95.0} for m in (10, 11, 12)] + \
               [{"date": f"2026-{m:02d}-15", "amount": 95.0} for m in range(1, 9)]
    res = invoice_result(supplier="ZSE", identifiers=[{"kind": "EIC", "value": "24ZZS7001255000R"}, {"kind": "variabilny_symbol", "value": "6310803049"}],
                         invoice={"number": "7142118169", "kind": "vyuctovanie", "issued_at": "2026-09-08", "period_from": "2025-09-01",
                                  "period_to": "2026-08-31", "due_at": "2026-09-22", "total": 1873.37, "to_pay": 579.09, "advances": 1045.0,
                                  "consumption": 11502, "unit": "kWh", "unit_price": 0.146, "fixed_monthly": 16.11, "variable_symbol": "6310803049",
                                  "generation": {"kwh": 6364.79, "amount": 285.30, "fee": 36.0},
                                  "next_advance": {"amount": 245.0, "per_months": 1, "first_due": "2026-10-15"},
                                  "advance_payments": advances})
    # one advance is already known from a bank statement uploaded earlier (rule → service)
    monkeypatch.setattr(extract, "extract", lambda *a, **k: _statement([
        {"date": "2026-07-15", "amount": -95.0, "currency": "EUR", "counterparty": "Energetika Slovensko",
         "counterparty_iban": "SK7211000000002649000047", "variable_symbol": "6310803049", "note": "inkaso"}], "2026-07-31"))
    st1, _ = documents.store("vypis-07.pdf", PDF + b"st07", "application/pdf", "upload")
    documents.process(st1["id"])
    t1 = db.row(db.q1("SELECT * FROM transactions"))
    bank.assign_transaction(t1["id"], 1, service_id=s["id"], category="elektrina", remember=True)
    assert db.q1("SELECT COUNT(*) c FROM costs")["c"] == 1

    d = _process(monkeypatch, res, "zse-bela.pdf")
    assert d["status"] == "done"
    rows = _costs(d["id"])
    assert [r["amount"] for r in rows if r["kind"] == "faktura"] == [579.09]
    assert len([r for r in rows if r["kind"] == "zaloha"]) == 10          # 11 listed, July already there
    assert round(sum(r["amount"] for r in db.rows(db.q("SELECT amount FROM costs"))), 2) == round(1045 + 579.09, 2)
    inv = db.row(db.q1("SELECT * FROM invoices WHERE document_id=?", (d["id"],)))
    assert inv["generation_kwh"] == 6364.79 and inv["generation_amount"] == 285.30 and inv["generation_fee"] == 36.0
    assert _service(s["id"])["monthly_estimate"] == 245.0

    # a later statement with the August advance: the rule assigns it to the listed row, no new cost;
    # the transfer 45 days around the vyúčtovanie is still a cost (it is not the bill's payment)
    monkeypatch.setattr(extract, "extract", lambda *a, **k: _statement([
        {"date": "2026-08-17", "amount": -95.0, "currency": "EUR", "counterparty": "Energetika Slovensko",
         "counterparty_iban": "SK7211000000002649000047", "variable_symbol": "6310803049", "note": "inkaso"},
        {"date": "2026-09-22", "amount": -579.09, "currency": "EUR", "counterparty": "Energetika Slovensko",
         "counterparty_iban": "SK7211000000002649000047", "variable_symbol": "6310803049", "note": "inkaso"}], "2026-09-30"))
    st2, _ = documents.store("vypis-09.pdf", PDF + b"st09", "application/pdf", "upload")
    documents.process(st2["id"])
    statuses = {t["date"]: t["status"] for t in db.rows(db.q("SELECT * FROM transactions"))}
    assert statuses == {"2026-07-15": "assigned", "2026-08-17": "assigned", "2026-09-22": "invoice"}
    aug = db.row(db.q1("SELECT c.* FROM costs c JOIN transactions t ON t.cost_id=c.id WHERE t.date='2026-08-17'"))
    assert aug["kind"] == "zaloha" and aug["document_id"] == d["id"]
    assert round(sum(r["amount"] for r in db.rows(db.q("SELECT amount FROM costs"))), 2) == round(1045 + 579.09, 2)
    assert db.q1("SELECT paid_at FROM invoices WHERE document_id=?", (d["id"],))["paid_at"] == "2026-09-22"

    # reading the bill again keeps the linked August row (now the transfer's own) and adds nothing twice
    monkeypatch.setattr(extract, "extract", lambda *a, **k: __import__("json").loads(__import__("json").dumps(res)))
    documents.reprocess(d["id"]); documents.process(d["id"])
    assert round(sum(r["amount"] for r in db.rows(db.q("SELECT amount FROM costs"))), 2) == round(1045 + 579.09, 2)
    aug = db.row(db.q1("SELECT c.* FROM costs c JOIN transactions t ON t.cost_id=c.id WHERE t.date='2026-08-17'"))
    assert aug["kind"] == "prevod" and aug["document_id"] == st2["id"]
    assert db.q1("SELECT COUNT(*) c FROM costs WHERE document_id=? AND kind='zaloha'", (d["id"],))["c"] == 9
    doc = jano.get(f"/api/documents/{d['id']}").json()
    assert doc["invoice"]["generation_kwh"] == 6364.79


def test_advance_schedule_books_nothing_and_sets_the_monthly_estimate(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "plyn", supplier="SPP", identifier="SKSPPDIS000000000123")
    res = invoice_result(supplier="SPP", service_kind="plyn", identifiers=[{"kind": "POD", "value": "SKSPPDIS000000000123"}],
                         invoice={"kind": "zalohova", "issued_at": "2026-09-01", "period_from": "2026-09-01", "period_to": "2027-08-31",
                                  "due_at": "2026-09-15", "total": 62.0, "to_pay": 62.0, "consumption": None, "unit": "kWh", "unit_price": None,
                                  "fixed_monthly": None})
    d = _process(monkeypatch, res, "spp-zalohy.pdf")
    assert d["status"] == "done" and _costs(d["id"]) == []
    assert _service(s["id"])["monthly_estimate"] == 62.0
    assert jano.get("/api/dashboard?month=2026-09").json()["due"] == []
    sep = next(x for pl in jano.get("/api/dashboard?month=2026-09").json()["places"] for x in pl["services"])
    assert sep["source"] == "odhad" and sep["amount"] == 62.0


def test_absurd_schedule_and_advance_values_are_ignored(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE", identifier="24ZZS5015208000N", monthly_estimate=30.0)
    res = invoice_result(identifiers=[{"kind": "EIC", "value": "24ZZS5015208000N"}],
                         invoice={"kind": "vyuctovanie", "issued_at": "2026-08-16", "period_from": "2025-08-14", "period_to": "2026-08-11",
                                  "total": 267.56, "to_pay": 113.56, "advances": 154.0,
                                  "next_advance": {"amount": 1e9, "per_months": 0, "first_due": "x"},
                                  "advance_payments": [{"date": "2031-01-01", "amount": 77.0}, {"date": "2025-10-02", "amount": -77.0},
                                                       {"date": "2025-10-02", "amount": 77.0}, {"date": "2026-03-02", "amount": 77.0}]})
    d = _process(monkeypatch, res, "zse-byt1.pdf")
    rows = _costs(d["id"])
    assert sorted(r["amount"] for r in rows) == [77.0, 77.0, 113.56]
    assert _service(s["id"])["monthly_estimate"] == 22.3      # 267,56 / 12 — the broken schedule did not win
    assert db.q1("SELECT advance_amount FROM invoices WHERE document_id=?", (d["id"],))["advance_amount"] is None
