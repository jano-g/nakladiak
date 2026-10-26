"""Domain flows through the HTTP API with the Claude call mocked."""
import time

from app import db
from app.services import documents, extract

from conftest import BASE, PDF, PNG, invoice_result, make_place, make_service


def _wait(c, did, timeout=10):
    for _ in range(int(timeout * 20)):
        d = c.get(f"/api/documents/{did}").json()
        if d["status"] in ("done", "needs_review", "error"):
            return d
        time.sleep(0.05)
    raise AssertionError("document did not finish")


def test_places_and_services_crud(jano):
    p = make_place(jano, "Dom v Belej", "dom", address="Belá 12", color="#aa5500")
    assert p["kind_label"] == "Dom"
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE", identifier="24ZZS1234567890A")
    assert s["unit"] == "kWh"
    r = jano.put(f"/api/services/{s['id']}", json={"unit_price": "0,24", "monthly_estimate": 60})
    assert r.status_code == 200 and r.json()["unit_price"] == 0.24
    assert jano.post("/api/services", json={"place_id": p["id"], "kind": "teleport"}).status_code == 400
    assert jano.post("/api/places", json={"name": "", "kind": "byt"}).status_code == 400
    assert jano.post("/api/places", json={"name": "X", "kind": "byt", "color": "red"}).status_code == 400
    lst = jano.get("/api/places").json()["places"]
    assert len(lst) == 1 and len(lst[0]["services"]) == 1
    assert jano.delete(f"/api/services/{s['id']}").json()["deactivated"] is False
    assert jano.put(f"/api/places/{p['id']}", json={"archived": True}).json()["archived"] == 1
    assert jano.get("/api/places").json()["places"] == []


def test_invoice_upload_matches_by_identifier_and_books_a_cost(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE Energia", identifier="24ZZS-1234567890A")
    monkeypatch.setattr(extract, "extract", lambda *a, **k: invoice_result())
    r = jano.post("/api/documents", files={"file": ("zse.pdf", PDF, "application/pdf")}, data={"kind": "auto"})
    assert r.status_code == 200, r.text
    did = r.json()["document"]["id"]
    d = _wait(jano, did)
    assert d["status"] == "done" and d["service_id"] == s["id"] and d["place_id"] == p["id"]
    assert d["match_how"] == "identifier"
    assert d["invoice"]["total"] == 84.5 and d["invoice"]["paid_at"] is None
    assert len(d["costs"]) == 1 and d["costs"][0]["amount"] == 84.5 and d["costs"][0]["category"] == "elektrina"
    # the service learned the tariff from the bill
    svc = jano.get(f"/api/services/{s['id']}").json()
    assert svc["unit_price"] == 0.21 and svc["fixed_monthly"] == 9.5
    # same file again = duplicate, no second cost
    r2 = jano.post("/api/documents", files={"file": ("zse-copy.pdf", PDF, "application/pdf")})
    assert r2.json()["duplicate"] is True
    assert db.q1("SELECT COUNT(*) c FROM costs")["c"] == 1
    dash = jano.get("/api/dashboard?month=2026-10").json()
    assert dash["total"] == 84.5 and dash["places"][0]["services"][0]["source"] == "faktura"


def test_unknown_invoice_waits_for_review_and_learns_a_rule(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "plyn", supplier="SPP")
    res = invoice_result(supplier="SPP", service_kind="plyn", identifiers=[{"kind": "POD", "value": "SKSPPDIS000110011234"}],
                         matched_service_id=None, match_confidence=0.3)
    res["invoice"]["unit"] = "m3"
    monkeypatch.setattr(extract, "extract", lambda *a, **k: res)
    # two services of the same kind → supplier alone is not enough → review
    make_service(jano, make_place(jano, "Chalupa", "chalupa")["id"], "plyn", supplier="SPP")
    did = jano.post("/api/documents", files={"file": ("spp.pdf", PDF, "application/pdf")}).json()["document"]["id"]
    d = _wait(jano, did)
    assert d["status"] == "needs_review" and d["costs"] == []
    assert jano.get("/api/me").json()["pending"]["documents"] == 1
    r = jano.post(f"/api/documents/{did}/review", json={"service_id": s["id"], "remember": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "done" and d["service_id"] == s["id"] and len(d["costs"]) == 1
    rules = jano.get("/api/rules").json()["rules"]
    assert any(r["match_kind"] == "identifier" and r["pattern"] == "SKSPPDIS000110011234" for r in rules)
    # the next bill with the same POD goes through alone
    res2 = dict(res); res2["invoice"] = dict(res["invoice"], number="2026002", total=50.0)
    monkeypatch.setattr(extract, "extract", lambda *a, **k: res2)
    did2 = jano.post("/api/documents", files={"file": ("spp2.pdf", PDF + b"\n%2", "application/pdf")}).json()["document"]["id"]
    assert _wait(jano, did2)["status"] == "done"


def test_receipt_photo_needs_place_then_is_remembered_by_merchant(jano, monkeypatch):
    p = make_place(jano, "Dom v Belej", "dom")
    rc = BASE | {"doc_kind": "uctenka", "supplier": "Hornbach", "summary": "Hornbach 36,90 €",
                 "receipt": {"merchant": "HORNBACH Bratislava", "date": "2026-10-10", "total": 36.9, "currency": "EUR",
                             "category_hint": "udrzba", "items": [{"name": "Silikón", "amount": 6.9}]}}
    monkeypatch.setattr(extract, "extract", lambda *a, **k: dict(rc))
    did = jano.post("/api/documents", files={"file": ("IMG_1.png", PNG, "image/png")}).json()["document"]["id"]
    assert _wait(jano, did)["status"] == "needs_review"
    d = jano.post(f"/api/documents/{did}/review", json={"place_id": p["id"], "category": "udrzba", "remember": True}).json()
    assert d["status"] == "done" and d["costs"][0]["amount"] == 36.9 and d["costs"][0]["place_id"] == p["id"]
    did2 = jano.post("/api/documents", files={"file": ("IMG_2.png", PNG + b"x", "image/png")}).json()["document"]["id"]
    d2 = _wait(jano, did2)
    assert d2["status"] == "done" and d2["place_id"] == p["id"]
    assert jano.get("/api/dashboard?month=2026-10").json()["places"][0]["other"][0]["category"] == "udrzba"


def test_statement_pays_invoices_and_queues_unknown_transfers(jano, monkeypatch):
    p = make_place(jano)
    make_service(jano, p["id"], "elektrina", supplier="ZSE Energia", identifier="24ZZS1234567890A")
    monkeypatch.setattr(extract, "extract", lambda *a, **k: invoice_result())
    did = jano.post("/api/documents", files={"file": ("zse.pdf", PDF, "application/pdf")}).json()["document"]["id"]
    _wait(jano, did)
    st = BASE | {"doc_kind": "vypis", "summary": "Výpis 10/2026", "statement": {
        "account_iban": "SK89", "period_from": "2026-10-01", "period_to": "2026-10-31", "transactions": [
            {"date": "2026-10-15", "amount": -84.5, "currency": "EUR", "counterparty": "ZSE Energia a.s.", "counterparty_iban": "SK3112000000198742637541",
             "variable_symbol": "2026001", "note": "elektrina"},
            {"date": "2026-10-16", "amount": -120.0, "currency": "EUR", "counterparty": "Peter Záhradník", "counterparty_iban": "SK99",
             "variable_symbol": "", "note": "kosenie"},
            {"date": "2026-10-17", "amount": 1500.0, "currency": "EUR", "counterparty": "Zamestnávateľ", "counterparty_iban": "",
             "variable_symbol": "", "note": "mzda"},
        ]}}
    monkeypatch.setattr(extract, "extract", lambda *a, **k: dict(st))
    sid = jano.post("/api/documents", files={"file": ("vypis.pdf", PDF + b"\n%v", "application/pdf")}).json()["document"]["id"]
    d = _wait(jano, sid)
    assert d["status"] == "done"
    statuses = {t["counterparty"]: t["status"] for t in d["transactions"]}
    assert statuses == {"ZSE Energia a.s.": "invoice", "Peter Záhradník": "pending", "Zamestnávateľ": "ignored"}
    inv = jano.get(f"/api/documents/{did}").json()["invoice"]
    assert inv["paid_at"] == "2026-10-15"
    pend = jano.get("/api/transactions").json()["transactions"]
    assert len(pend) == 1
    t = jano.post(f"/api/transactions/{pend[0]['id']}/assign", json={"place_id": p["id"], "category": "zahrada", "remember": True}).json()
    assert t["status"] == "assigned"
    dash = jano.get("/api/dashboard?month=2026-10").json()
    assert dash["total"] == 84.5 + 120.0
    assert dash["pending"]["transactions"] == 0
    # same statement again: nothing doubles
    assert jano.post("/api/documents", files={"file": ("vypis-copy.pdf", PDF + b"\n%v", "application/pdf")}).json()["duplicate"]
    st2 = dict(st); st2["statement"] = dict(st["statement"], period_to="2026-11-30")
    monkeypatch.setattr(extract, "extract", lambda *a, **k: st2)
    sid2 = jano.post("/api/documents", files={"file": ("vypis2.pdf", PDF + b"\n%v2", "application/pdf")}).json()["document"]["id"]
    _wait(jano, sid2)
    assert db.q1("SELECT COUNT(*) c FROM transactions")["c"] == 3
    assert db.q1("SELECT COUNT(*) c FROM costs")["c"] == 2


def test_extraction_failure_backs_off_and_can_be_retried(jano, monkeypatch):
    def boom(*a, **k):
        raise extract.ExtractError("Claude API je nedostupné (sieť).")
    monkeypatch.setattr(extract, "extract", boom)
    did = jano.post("/api/documents", files={"file": ("x.pdf", PDF, "application/pdf")}).json()["document"]["id"]
    d = _wait(jano, did)
    assert d["status"] == "error" and "nedostupné" in d["error"] and d["attempts"] == 1
    assert documents.process_next() is False  # next try is scheduled minutes later, not now
    monkeypatch.setattr(extract, "extract", lambda *a, **k: dict(BASE))
    jano.post(f"/api/documents/{did}/reprocess", json={"hint": "je to zmluva"})
    d = _wait(jano, did)
    assert d["status"] == "needs_review" and d["review_note"] == "je to zmluva"
    assert jano.post(f"/api/documents/{did}/review", json={"kind": "ine"}).json()["status"] == "done"
    assert jano.delete(f"/api/documents/{did}").json()["ok"]
    assert jano.get(f"/api/documents/{did}").status_code == 404


def test_upload_rejects_wrong_types(jano):
    assert jano.post("/api/documents", files={"file": ("x.exe", b"MZ\x00\x00", "application/octet-stream")}).status_code == 400
    assert jano.post("/api/documents", files={"file": ("x.pdf", b"", "application/pdf")}).status_code == 400


def test_dashboard_estimates_from_readings(jano):
    p = make_place(jano, "Dom v Belej", "dom")
    s = make_service(jano, p["id"], "elektrina", unit_price=0.2, fixed_monthly=10, connector="zsd", connector_ref="123")
    with db.tx():
        for day in range(1, 11):
            db.run("INSERT INTO readings(service_id,date,kind,value,intervals,source,updated_at) VALUES(?,?,?,?,96,'zsd',?)",
                   (s["id"], f"2026-10-{day:02d}", "consumption", 10.0, db.now_iso()))
    from datetime import date
    from app.services import costs
    dash = costs.dashboard("2026-10", today=date(2026, 10, 10))
    item = dash["places"][0]["services"][0]
    assert item["source"] == "odhad" and item["how"] == "spotreba"
    assert item["consumption"] == 310.0 and item["amount"] == round(310 * 0.2 + 10, 2)
    assert item["week"]["value"] == 70.0 and item["month"]["value"] == 100.0
    assert dash["estimated"] == item["amount"]


def test_manual_cost_and_history(jano):
    p = make_place(jano)
    r = jano.post("/api/costs", json={"place_id": p["id"], "amount": "45,00", "category": "upratovanie", "date": "2026-10-03", "counterparty": "Marta"})
    assert r.status_code == 200 and r.json()["amount"] == 45.0
    assert jano.post("/api/costs", json={"place_id": p["id"], "amount": "abc"}).status_code == 400
    assert jano.get("/api/costs?month=2026-10").json()["costs"][0]["place_name"] == "Byt Bratislava"
    h = jano.get("/api/history").json()["history"]
    assert h[0]["label"] == "Pridal(a) výdavok"
    assert jano.delete(f"/api/costs/{r.json()['id']}").json()["ok"]


def test_about_and_meta(jano):
    a = jano.get("/api/about").json()
    assert a["changes"] and a["changes"][0]["items"]
    m = jano.get("/api/meta").json()
    assert any(k["id"] == "elektrina" for k in m["service_kinds"])
