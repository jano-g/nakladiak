"""Pure-function checks: ZSD aggregation, bank fingerprints, util helpers."""
from datetime import date

from app import util
from app.connectors import zsd_fetch
from app.services import bank


def test_zsd_daily_totals_sum_quarter_hours():
    data = {"data": {"profileData": {"dailyIntervalData": [
        {"date": "2026-10-20", "values": [{"measuredValue": 2.0}] * 96},
        {"date": "2026-10-21", "values": [{"measuredValue": "1.0"}] * 50},
        {"date": "2026-10-22", "values": []},
    ]}}}
    t = zsd_fetch.daily_totals(data)
    assert t["2026-10-20"] == [48.0, 96] and t["2026-10-21"] == [12.5, 50] and "2026-10-22" not in t
    assert zsd_fetch.daily_totals({}) == {}


def test_zsd_role_classification():
    assert zsd_fetch.classify_role({"roleId": "PS_PLUS", "description": "Činný výkon dodávka"}) == "generation"
    assert zsd_fetch.classify_role({"roleId": "X", "description": "Jalová dodávka pri odbere"}) == "reactive"
    assert zsd_fetch.classify_role({"roleId": "PS_MINUS", "description": "Činný výkon odber"}) == "consumption"
    assert zsd_fetch.role_code({"roleId": "PS_PLUS", "description": "x"}) == "PS_PLUS"


def test_bank_fingerprint_is_stable_and_order_independent():
    a = {"date": "2026-10-01", "amount": -12.5, "counterparty": "X", "counterparty_iban": "", "variable_symbol": "1", "note": "n"}
    b = {"note": "n", "variable_symbol": "1", "counterparty_iban": "", "counterparty": "X", "amount": -12.5, "date": "2026-10-01"}
    assert bank._fingerprint(a) == bank._fingerprint(b)
    assert bank._fingerprint(dict(a, amount=-12.51)) != bank._fingerprint(a)


def test_util_helpers():
    assert util.norm_identifier("24ZZS-1234 5678/90a") == "24ZZS1234567890A"
    assert util.fold("ZSE Energia, a.s.") == "zse energia, a.s."
    assert util.to_float("1 234,50") == 1234.5 and util.to_float("nan") is None and util.to_float("") is None
    assert util.month_end(date(2026, 2, 1)) == date(2026, 2, 28)
    assert util.add_months(date(2026, 1, 15), -1) == date(2025, 12, 1)
    assert util.fmt_eur(1234.5) == "1 234,50 €"
    assert util.plural(3, "deň", "dni", "dní") == "3 dni"
