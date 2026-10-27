import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_tmp = tempfile.mkdtemp(prefix="nakladiak-test-")
os.environ.update({
    "DATA_DIR": _tmp, "NAKLADIAK_DB": os.path.join(_tmp, "nakladiak.db"), "NAKLADIAK_DOCS": os.path.join(_tmp, "docs"),
    "APP_URL": "http://testserver", "APP_TZ": "Europe/Bratislava", "NAKLADIAK_NO_SCHEDULER": "1",
    "ADMIN_USERNAME": "jano", "ADMIN_NAME": "Jano", "ADMIN_EMAIL": "jano@example.com", "ADMIN_PASSWORD": "testheslo123",
    "SMTP_HOST": "", "ANTHROPIC_API_KEY": "", "IMAP_HOST": "", "ZSD_USER": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

H = {"X-Requested-With": "nakladiak"}

# A tiny valid PDF and PNG for uploads.
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000" "1f15c4890000000d49444154789c63f8ffff3f0005fe02fea7b2a0000000000049454e44ae426082")


@pytest.fixture(scope="session", autouse=True)
def _schema():
    from app import auth
    db.init()
    auth.bootstrap_users()


@pytest.fixture(scope="session")
def client():
    with TestClient(app, headers=H) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_tables():
    yield
    with db.tx():
        for t in ("transactions", "costs", "invoices", "documents", "readings", "rules", "services", "places",
                  "connector_runs", "history", "reminders_sent"):
            db.run(f"DELETE FROM {t}")
        db.run("DELETE FROM settings")
        db.run("DELETE FROM users WHERE username<>'jano'")
        db.run("UPDATE users SET is_admin=1, active=1, must_change_password=0, ntfy_topic='', email='jano@example.com' WHERE username='jano'")


def login(client, username="jano", password="testheslo123"):
    c = TestClient(app, headers=H, follow_redirects=False)
    r = c.post("/login", data={"username": username, "password": password, "next": "/"})
    assert r.status_code == 303, r.text
    return c


@pytest.fixture
def jano(client):
    return login(client, "jano")


def make_place(c, name="Byt Bratislava", kind="byt", **extra):
    r = c.post("/api/places", json={"name": name, "kind": kind, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def make_service(c, place_id, kind="elektrina", **extra):
    r = c.post("/api/services", json={"place_id": place_id, "kind": kind, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def fake_extract(result: dict):
    """A stand-in for services.extract.extract returning a fixed answer (deep-copied)."""
    def _fn(path, mime, places, services, hint=""):
        return json.loads(json.dumps(result))
    return _fn


BASE = {"doc_kind": "ine", "supplier": None, "service_kind": None, "place_hint": None, "identifiers": [],
        "matched_service_id": None, "matched_place_id": None, "match_confidence": 0.0,
        "invoice": None, "receipt": None, "statement": None, "summary": "Neznámy dokument"}


def invoice_result(**over):
    inv = {"number": "2026001", "kind": "pravidelna", "issued_at": "2026-10-05", "period_from": "2026-09-01",
           "period_to": "2026-09-30", "due_at": "2026-10-20", "total": 84.5, "to_pay": 84.5, "advances": None,
           "currency": "EUR", "consumption": 310.0, "unit": "kWh", "unit_price": 0.21, "fixed_monthly": 9.5,
           "variable_symbol": "2026001", "iban": "SK3112000000198742637541",
           "generation": None, "next_advance": None, "advance_payments": []}
    inv.update(over.pop("invoice", {}))
    return BASE | {"doc_kind": "faktura", "supplier": "ZSE Energia", "service_kind": "elektrina",
                   "identifiers": [{"kind": "EIC", "value": "24ZZS1234567890A"}], "match_confidence": 0.9,
                   "invoice": inv, "summary": "ZSE Energia, elektrina 9/2026, 84,50 €"} | over
