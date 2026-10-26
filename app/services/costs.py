"""Dashboard numbers: what did this month cost, per place and service, what is estimated
from metered consumption, what is still coming (unpaid invoices), consumption series."""
from datetime import date, timedelta

from .. import db, util

SERVICE_LABELS = {"elektrina": "Elektrina", "plyn": "Plyn", "voda": "Voda", "internet": "Internet", "tv": "TV",
                  "mobil": "Mobil", "odpad": "Odpad", "kurenie": "Kúrenie", "poistenie": "Poistenie", "najom": "Nájom",
                  "udrzba": "Údržba", "zahrada": "Záhrada", "upratovanie": "Upratovanie", "spravca": "Správca",
                  "dane": "Dane", "nakup": "Nákup", "ine": "Iné"}


def _month_bounds(ym: str) -> tuple[date, date]:
    y, m = int(ym[:4]), int(ym[5:7])
    start = date(y, m, 1)
    return start, util.month_end(start)


def service_consumption(service_id: int, start: date, end: date, kind: str = "consumption") -> dict:
    r = db.q1("SELECT COALESCE(SUM(value),0) v, COUNT(*) n, MAX(date) last FROM readings WHERE service_id=? AND kind=? AND date BETWEEN ? AND ?",
              (service_id, kind, start.isoformat(), end.isoformat()))
    return {"value": round(r["v"], 2), "days": r["n"], "last": r["last"]}


def estimate_for_month(service: dict, ym: str, today: date) -> dict | None:
    """For a metered service with no invoice in the month: readings × unit price + fixed fee,
    projected to the whole month when the month is still running."""
    start, end = _month_bounds(ym)
    cons = service_consumption(service["id"], start, min(end, today))
    if cons["days"] == 0:
        if service.get("monthly_estimate"):
            return {"amount": service["monthly_estimate"], "how": "zaloha"}
        return None
    days_elapsed = max(1, (min(end, today) - start).days + 1)
    days_total = (end - start).days + 1
    projected = cons["value"] / cons["days"] * days_total if end > today else cons["value"]
    if service.get("unit_price"):
        amount = projected * service["unit_price"] + (service.get("fixed_monthly") or 0)
        return {"amount": round(amount, 2), "how": "spotreba", "consumption": round(projected, 1),
                "unit": service.get("unit") or "kWh", "measured_days": cons["days"], "days_elapsed": days_elapsed}
    if service.get("monthly_estimate"):
        return {"amount": service["monthly_estimate"], "how": "zaloha", "consumption": round(projected, 1),
                "unit": service.get("unit") or "kWh", "measured_days": cons["days"]}
    return {"amount": None, "how": "bez_ceny", "consumption": round(projected, 1), "unit": service.get("unit") or "kWh",
            "measured_days": cons["days"]}


def dashboard(ym: str, today: date | None = None) -> dict:
    today = today or util.today_local()
    start, end = _month_bounds(ym)
    places = db.rows(db.q("SELECT * FROM places WHERE archived=0 ORDER BY sort, id"))
    services = db.rows(db.q("SELECT * FROM services WHERE active=1 ORDER BY place_id, kind, id"))
    costs = db.rows(db.q("SELECT * FROM costs WHERE date BETWEEN ? AND ?", (start.isoformat(), end.isoformat())))
    by_service: dict[int, float] = {}
    by_place_other: dict[int, list] = {}
    for c in costs:
        if c["service_id"]:
            by_service[c["service_id"]] = by_service.get(c["service_id"], 0) + c["amount"]
        else:
            by_place_other.setdefault(c["place_id"], []).append(c)
    week_start = today - timedelta(days=6)
    out_places = []
    total = 0.0
    total_estimated = 0.0
    for p in places:
        pl = {"id": p["id"], "name": p["name"], "kind": p["kind"], "color": p["color"], "services": [], "other": [],
              "total": 0.0, "estimated": 0.0}
        for s in [x for x in services if x["place_id"] == p["id"]]:
            item = {"id": s["id"], "kind": s["kind"], "label": SERVICE_LABELS.get(s["kind"], s["kind"]), "name": s["label"],
                    "supplier": s["supplier"], "unit": s["unit"], "connector": s["connector"]}
            if s["id"] in by_service:
                item["amount"], item["source"] = round(by_service[s["id"]], 2), "faktura"
            else:
                est = estimate_for_month(s, ym, today)
                if est:
                    item.update(est)
                    item["source"] = "odhad"
                    if est.get("amount") is not None:
                        pl["estimated"] += est["amount"]
                else:
                    item["amount"], item["source"] = None, "nic"
            if s["connector"]:
                item["week"] = service_consumption(s["id"], week_start, today)
                item["month"] = service_consumption(s["id"], start, min(end, today))
                gen = service_consumption(s["id"], start, min(end, today), "generation")
                if gen["days"]:
                    item["generation_month"] = gen
            if item.get("amount") is not None:
                pl["total"] += item["amount"]
            pl["services"].append(item)
        for c in by_place_other.get(p["id"], []):
            pl["other"].append({"id": c["id"], "kind": c["kind"], "category": c["category"],
                                "label": SERVICE_LABELS.get(c["category"], c["category"] or "Iné"),
                                "counterparty": c["counterparty"], "amount": round(c["amount"], 2), "date": c["date"],
                                "document_id": c["document_id"]})
            pl["total"] += c["amount"]
        pl["total"] = round(pl["total"], 2)
        pl["estimated"] = round(pl["estimated"], 2)
        total += pl["total"]
        total_estimated += pl["estimated"]
        out_places.append(pl)
    unassigned = [c for c in costs if not c["place_id"]]
    return {
        "month": ym, "month_label": util.fmt_month(ym), "today": today.isoformat(),
        "is_current": start <= today <= end,
        "total": round(total, 2), "estimated": round(total_estimated, 2),
        "places": out_places,
        "unassigned_total": round(sum(c["amount"] for c in unassigned), 2),
        "history": monthly_history(util.add_months(start, -11), start),
        "pending": pending_counts(),
        "due": due_invoices(today),
    }


def monthly_history(first: date, last: date) -> list[dict]:
    rows = db.rows(db.q("SELECT substr(date,1,7) ym, place_id, SUM(amount) s FROM costs WHERE date>=? AND date<=? "
                        "GROUP BY ym, place_id", (first.isoformat(), util.month_end(last).isoformat())))
    months = []
    d = first
    while d <= last:
        ym = d.strftime("%Y-%m")
        months.append({"month": ym, "label": util.SK_MONTHS[d.month - 1][:3], "total": 0.0, "by_place": {}})
        d = util.add_months(d, 1)
    idx = {m["month"]: m for m in months}
    for r in rows:
        m = idx.get(r["ym"])
        if not m:
            continue
        m["total"] = round(m["total"] + r["s"], 2)
        m["by_place"][str(r["place_id"] or 0)] = round(r["s"], 2)
    return months


def pending_counts() -> dict:
    return {
        "documents": db.q1("SELECT COUNT(*) c FROM documents WHERE status='needs_review'")["c"],
        "processing": db.q1("SELECT COUNT(*) c FROM documents WHERE status IN ('new','processing') OR (status='error' AND attempts<4)")["c"],
        "errors": db.q1("SELECT COUNT(*) c FROM documents WHERE status='error' AND attempts>=4")["c"],
        "transactions": db.q1("SELECT COUNT(*) c FROM transactions WHERE status='pending'")["c"],
    }


def due_invoices(today: date, days: int = 21) -> list[dict]:
    rows = db.rows(db.q(
        "SELECT i.*, s.kind service_kind, s.label service_label, p.name place_name, p.id place_id FROM invoices i "
        "LEFT JOIN services s ON s.id=i.service_id LEFT JOIN places p ON p.id=s.place_id "
        "WHERE i.paid_at IS NULL AND i.due_at IS NOT NULL AND i.due_at<=? AND COALESCE(i.to_pay,i.total)>0 "
        "ORDER BY i.due_at", ((today + timedelta(days=days)).isoformat(),)))
    return [{"id": r["id"], "document_id": r["document_id"], "supplier": r["supplier"], "due_at": r["due_at"],
             "amount": round(r["to_pay"] if r["to_pay"] is not None else r["total"], 2),
             "service": SERVICE_LABELS.get(r["service_kind"], r["service_kind"] or ""), "place": r["place_name"],
             "overdue": r["due_at"] < today.isoformat()} for r in rows]


def series(service_id: int, start: date, end: date) -> list[dict]:
    rows = db.rows(db.q("SELECT date, kind, value FROM readings WHERE service_id=? AND date BETWEEN ? AND ? ORDER BY date",
                        (service_id, start.isoformat(), end.isoformat())))
    out: dict[str, dict] = {}
    for r in rows:
        out.setdefault(r["date"], {"date": r["date"]})[r["kind"]] = round(r["value"], 2)
    return list(out.values())


def place_detail(place_id: int, months: int = 12) -> dict:
    today = util.today_local()
    first = util.add_months(util.month_start(today), -(months - 1))
    rows = db.rows(db.q(
        "SELECT substr(date,1,7) ym, COALESCE(service_id,0) sid, category, SUM(amount) s FROM costs "
        "WHERE place_id=? AND date>=? GROUP BY ym, sid, category ORDER BY ym", (place_id, first.isoformat())))
    return {"from": first.isoformat(), "rows": rows}
