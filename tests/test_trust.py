"""Model output and mail attachments are untrusted input: what may book automatically and what waits."""
from fastapi.testclient import TestClient

from app import db, settings
from app.main import app
from app.services import documents, extract

from conftest import H, PDF, invoice_result, login, make_place, make_service


def _mail_doc(name: str, sender: str = "faktury@zse.sk"):
    doc, created = documents.store(name, PDF + name.encode(), "application/pdf", "mail", mail_key="uv:" + name,
                                   mail_from=sender, mail_subject="Faktúra")
    assert created
    return doc


def test_mail_invoice_books_only_with_a_known_identifier(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE Energia", identifier="24ZZS1234567890A")
    # identifier matches → books
    monkeypatch.setattr(extract, "extract", lambda *a, **k: invoice_result())
    d = documents.process(_mail_doc("a.pdf")["id"])
    assert d["status"] == "done" and d["service_id"] == s["id"]
    # same supplier, but only the model's guess / supplier-name match → waits for the user
    res = invoice_result(identifiers=[], matched_service_id=s["id"], match_confidence=0.97)
    res["invoice"]["number"] = "2"
    monkeypatch.setattr(extract, "extract", lambda *a, **k: res)
    d = documents.process(_mail_doc("b.pdf")["id"])
    assert d["status"] == "needs_review" and d["data"]["hold_reason"]
    assert db.q1("SELECT COUNT(*) c FROM costs WHERE document_id=?", (d["id"],))["c"] == 0
    # an upload from the logged-in user with the same data books (supplier match, one candidate)
    r = jano.post("/api/documents", files={"file": ("c.pdf", PDF + b"c", "application/pdf")})
    import time
    for _ in range(100):
        dd = jano.get(f"/api/documents/{r.json()['document']['id']}").json()
        if dd["status"] in ("done", "needs_review", "error"):
            break
        time.sleep(0.05)
    assert dd["status"] == "done"


def test_unknown_sender_never_books_when_allowlist_is_set(jano, monkeypatch):
    p = make_place(jano)
    make_service(jano, p["id"], "elektrina", supplier="ZSE Energia", identifier="24ZZS1234567890A")
    settings.set_("imap_allowed_senders", "zse.sk, jano@silnereci.sk")
    monkeypatch.setattr(extract, "extract", lambda *a, **k: invoice_result())
    assert documents.process(_mail_doc("x.pdf", "evil@attacker.example")["id"])["status"] == "needs_review"
    assert documents.process(_mail_doc("y.pdf", "ZSE <faktury@mail.zse.sk>")["id"])["status"] == "done"
    assert documents.sender_allowed("Jano <jano@silnereci.sk>") and not documents.sender_allowed("jano@silnereci.sk.evil.example")


def test_absurd_model_values_are_bounded_and_do_not_poison_prices(jano, monkeypatch):
    p = make_place(jano)
    s = make_service(jano, p["id"], "elektrina", supplier="ZSE Energia", identifier="24ZZS1234567890A", unit_price=0.2)
    res = invoice_result(invoice={"total": 1e15, "to_pay": 1e15, "issued_at": "not-a-date", "due_at": "2026-13-45",
                                  "currency": "<b>x</b>", "unit_price": 99999, "fixed_monthly": -5})
    monkeypatch.setattr(extract, "extract", lambda *a, **k: res)
    r = jano.post("/api/documents", files={"file": ("big.pdf", PDF, "application/pdf")})
    import time
    for _ in range(100):
        d = jano.get(f"/api/documents/{r.json()['document']['id']}").json()
        if d["status"] in ("done", "needs_review", "error"):
            break
        time.sleep(0.05)
    assert d["status"] == "needs_review" and "suma" in d["data"]["hold_reason"]
    inv = db.row(db.q1("SELECT * FROM invoices WHERE document_id=?", (d["id"],)))
    assert inv["total"] == 0 and inv["issued_at"] is None and inv["due_at"] is None and inv["currency"] == "EUR"
    svc = db.row(db.q1("SELECT * FROM services WHERE id=?", (s["id"],)))
    assert svc["unit_price"] == 0.2 and svc["fixed_monthly"] is None


def test_unknown_bytes_are_rejected_whatever_the_declared_type(jano):
    r = jano.post("/api/documents", files={"file": ("x.png", b"<html><script>alert(1)</script>", "image/png")})
    assert r.status_code == 400


def test_assign_rejects_foreign_keys_cleanly(jano, monkeypatch):
    p = make_place(jano)
    other = make_place(jano, "Chalupa", "chalupa")
    s = make_service(jano, other["id"], "voda", supplier="ZsVS")
    with db.tx():
        did = db.run("INSERT INTO documents(kind,status,source,filename,path,mime,size,sha256,received_at,created_at,updated_at) "
                     "VALUES('vypis','done','upload','v.pdf','x','application/pdf',1,'sha-v',?,?,?)", (db.now_iso(),) * 3)
        tid = db.run("INSERT INTO transactions(document_id,date,amount,currency,counterparty,fingerprint,status,created_at) "
                     "VALUES(?,?,?,?,?,?,?,?)", (did, "2026-10-01", -10, "EUR", "X", "fp-x", "pending", db.now_iso()))
    assert jano.post(f"/api/transactions/{tid}/assign", json={"place_id": 999999, "category": "ine"}).status_code == 400
    assert jano.post(f"/api/transactions/{tid}/assign", json={"place_id": p["id"], "service_id": s["id"], "category": "ine"}).status_code == 400
    assert jano.post("/api/costs", json={"place_id": p["id"], "service_id": s["id"], "amount": 5}).status_code == 400
    assert jano.post(f"/api/transactions/{tid}/assign", json={"place_id": other["id"], "service_id": s["id"], "category": "voda"}).status_code == 200


def test_connector_details_only_for_admin(jano):
    with db.tx():
        db.run("INSERT INTO connector_runs(connector,started_at,finished_at,ok,message,details) VALUES('zsd',?,?,0,'chyba','SECRET-STDERR')",
               (db.now_iso(), db.now_iso()))
    jano.post("/api/users", json={"username": "lucia", "mode": "password", "password": "lucia12345", "must_change_password": False})
    lucia = login(jano, "lucia", "lucia12345")
    assert "SECRET-STDERR" not in lucia.get("/api/connectors/status").text
    assert "SECRET-STDERR" in jano.get("/api/connectors/status").text


def test_file_route_sets_filename_and_sandbox(jano, monkeypatch):
    monkeypatch.setattr(extract, "extract", lambda *a, **k: invoice_result())
    did = jano.post("/api/documents", files={"file": ("účet ZSE.pdf", PDF, "application/pdf")}).json()["document"]["id"]
    r = jano.get(f"/api/documents/{did}/file")
    assert r.status_code == 200 and 'filename="ucet_zse.pdf"' in r.headers["content-disposition"]
    assert "sandbox" in r.headers["content-security-policy"]


def test_email_change_needs_password_and_login_page_ignores_free_text(jano):
    assert jano.put("/api/profile", json={"email": "new@example.com"}).status_code == 400
    assert jano.put("/api/profile", json={"email": "new@example.com", "current": "testheslo123"}).status_code == 200
    jano.put("/api/profile", json={"email": "jano@example.com", "current": "testheslo123"})
    anon = TestClient(app, follow_redirects=False)
    assert "zavolajte" not in anon.get("/login?error=zavolajte+123").text
    assert anon.head("/forgot").status_code == 200
    r = TestClient(app, headers=H, follow_redirects=False).post("/login", data={"username": "moje-tajne-heslo", "password": "x", "next": "/"})
    assert r.status_code == 401
    assert "moje-tajne-heslo" not in jano.get("/api/history").text
