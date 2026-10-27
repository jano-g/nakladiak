"""Read a bill / receipt / bank statement with Claude and return structured data.

One request per document: the PDF (document block) or photo (image block, downscaled) plus
the list of known places and services, so the model can both extract the fields and say which
service the document most likely belongs to. The response is constrained to SCHEMA via
structured outputs, so the caller gets valid JSON or an exception — never prose."""
import base64
import io
import json
import logging
from pathlib import Path

from .. import settings

log = logging.getLogger(__name__)

SERVICE_KINDS = ["elektrina", "plyn", "voda", "internet", "tv", "mobil", "odpad", "kurenie",
                 "poistenie", "najom", "udrzba", "ine"]
MAX_IMAGE_SIDE = 2000
MAX_IMAGE_PIXELS = 25_000_000  # decompression-bomb ceiling for uploads (headpop lesson); checked before decoding


class ExtractError(RuntimeError):
    pass


def _nullable(t: str, **extra) -> dict:
    return {"type": [t, "null"], **extra}


_DATE = _nullable("string", description="ISO dátum YYYY-MM-DD alebo null")
_NUM = _nullable("number")
_STR = _nullable("string")

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "doc_kind": {"type": "string", "enum": ["faktura", "uctenka", "vypis", "ine"]},
        "supplier": _STR,
        "service_kind": {"type": ["string", "null"], "enum": SERVICE_KINDS + [None]},
        "place_hint": _STR,
        "identifiers": {
            "type": "array",
            "items": {"type": "object", "additionalProperties": False,
                      "properties": {"kind": {"type": "string"}, "value": {"type": "string"}},
                      "required": ["kind", "value"]},
        },
        "matched_service_id": _nullable("integer"),
        "matched_place_id": _nullable("integer"),
        "match_confidence": {"type": "number"},
        "invoice": {
            "anyOf": [{"type": "null"}, {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "number": _STR,
                    "kind": {"type": "string", "enum": ["vyuctovanie", "zalohova", "pravidelna", "dobropis", "ine"]},
                    "issued_at": _DATE, "period_from": _DATE, "period_to": _DATE, "due_at": _DATE,
                    "total": {"type": "number"}, "to_pay": _NUM, "advances": _NUM,
                    "currency": {"type": "string"},
                    "consumption": _NUM, "unit": _STR, "unit_price": _NUM,
                    "fixed_monthly": _NUM,
                    "variable_symbol": _STR, "iban": _STR,
                    "generation": {"anyOf": [{"type": "null"}, {
                        "type": "object", "additionalProperties": False,
                        "properties": {"kwh": _NUM, "amount": _NUM, "fee": _NUM},
                        "required": ["kwh", "amount", "fee"]}]},
                    "next_advance": {"anyOf": [{"type": "null"}, {
                        "type": "object", "additionalProperties": False,
                        "properties": {"amount": {"type": "number"}, "per_months": {"type": "integer"}, "first_due": _DATE},
                        "required": ["amount", "per_months", "first_due"]}]},
                    "advance_payments": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {"date": {"type": "string"}, "amount": {"type": "number"}},
                        "required": ["date", "amount"]}},
                },
                "required": ["number", "kind", "issued_at", "period_from", "period_to", "due_at", "total",
                             "to_pay", "advances", "currency", "consumption", "unit", "unit_price",
                             "fixed_monthly", "variable_symbol", "iban", "generation", "next_advance",
                             "advance_payments"],
            }]
        },
        "receipt": {
            "anyOf": [{"type": "null"}, {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "merchant": _STR, "date": _DATE, "total": {"type": "number"}, "currency": {"type": "string"},
                    "category_hint": _STR,
                    "items": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                                          "properties": {"name": {"type": "string"}, "amount": _NUM},
                                                          "required": ["name", "amount"]}},
                },
                "required": ["merchant", "date", "total", "currency", "category_hint", "items"],
            }]
        },
        "statement": {
            "anyOf": [{"type": "null"}, {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "account_iban": _STR, "period_from": _DATE, "period_to": _DATE,
                    "transactions": {"type": "array", "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {"date": {"type": "string"}, "amount": {"type": "number"},
                                       "currency": {"type": "string"}, "counterparty": _STR,
                                       "counterparty_iban": _STR, "variable_symbol": _STR, "note": _STR},
                        "required": ["date", "amount", "currency", "counterparty", "counterparty_iban",
                                     "variable_symbol", "note"]}},
                },
                "required": ["account_iban", "period_from", "period_to", "transactions"],
            }]
        },
        "summary": {"type": "string"},
    },
    "required": ["doc_kind", "supplier", "service_kind", "place_hint", "identifiers", "matched_service_id",
                 "matched_place_id", "match_confidence", "invoice", "receipt", "statement", "summary"],
}

SYSTEM = """Si účtovný asistent slovenskej domácnosti. Dostaneš jeden dokument (PDF alebo fotku) a zoznam
známych miest a služieb. Vráť presne vyplnený JSON podľa schémy.

Pravidlá:
- doc_kind: "faktura" = faktúra/vyúčtovanie/zálohový predpis od dodávateľa (elektrina, plyn, voda, internet,
  TV, mobil, odpad, poistenie…); "uctenka" = pokladničný doklad z obchodu/servisu; "vypis" = výpis z bankového
  účtu; "ine" = čokoľvek iné.
- supplier: obchodná značka, pod ktorou dodávateľ vystupuje (ZSE, SPP, UPC, O2, Starlink, BVS), nie dlhý
  právny názov (napr. faktúru od Energetika Slovensko, a.s. so značkou ZSE označ "ZSE").
- Sumy sú čísla v eurách (bodka ako desatinný oddeľovač), vrátane DPH. Vo výpise je výdavok záporný, príjem kladný.
  Dokumenty môžu byť aj po anglicky (Starlink: "Invoice Date", "Total Due", "EUR 50,00").
- Dátumy vždy ako YYYY-MM-DD, aj z anglického zápisu ("Saturday, September 27, 2025" → 2025-09-27).
  Ak dátum chýba, null — nič nevymýšľaj.
- identifiers: všetko, čo identifikuje odberné miesto alebo zmluvu — s kind po slovensky: "EIC", "POD",
  "cislo_miesta_spotreby", "cislo_zmluvy", "variabilny_symbol", "cislo_zakaznika", "telefon", "zariadenie"
  (napr. KIT Starlinku). Pozor: zákaznícke číslo (ZSE „Zákaznícke číslo“, Starlink „Customer Account“) je
  spoločné pre všetky odberné miesta zákazníka, preto službu neurčuj len podľa neho — rozhoduje EIC, číslo
  miesta spotreby, variabilný symbol alebo adresa odberného miesta.
- service_kind podľa toho, čo sa fakturuje. Teplo/teplá voda od bytového družstva = "kurenie". Starlink = "internet".
- invoice.kind: "vyuctovanie" = ročné/periodické vyúčtovanie so započítanými zálohami; "pravidelna" = bežná
  faktúra za obdobie (mesačná, štvrťročná, polročná); "zalohova" = rozpis / predpis záloh bez vyúčtovania;
  "dobropis" = dobropis.
- total = celková fakturovaná suma za obdobie s DPH (pri vyúčtovaní „Dodávka a distribúcia“ za celé obdobie,
  bez odpočítania záloh). advances = súčet započítaných uhradených záloh (kladné číslo). to_pay = suma na
  úhradu: nedoplatok kladný, PREPLATOK ZÁPORNÝ (napr. "Suma na vrátenie (preplatok): −118,03 €" → -118.03).
- Ak jeden PDF obsahuje viac faktúr toho istého odberu a „Sumarizáciu“ (ZSE: faktúra za elektrinu + faktúra za
  výrobu odberateľská + faktúra za výrobu dodávateľská), invoice je hlavná faktúra za spotrebu a to_pay je
  „Suma na úhradu“ zo Sumarizácie (kladná = nedoplatok, záporná = preplatok). Do generation daj dodávku do
  siete: kwh = dodané kWh, amount = suma, ktorú dodávateľ platí za dodanú elektrinu (kladné číslo),
  fee = poplatok za odovzdávacie miesto. Inak generation = null.
- consumption: fakturovaná spotreba za obdobie v jednotkách unit (kWh, m3, GB). Pri elektrine spotrebu zrátaj zo
  všetkých taríf (VT + NT) a všetkých cenových období. unit_price = priemerná cena za jednotku s DPH BEZ fixných
  poplatkov: (suma za elektrinu/plyn s DPH − fixné mesačné platby s DPH) / spotreba. fixed_monthly = fixné
  mesačné poplatky s DPH za jeden mesiac (platba za odberné miesto + pevná zložka distribúcie), ak sú uvedené.
- next_advance: z tabuľky „Harmonogram budúcich preddavkových platieb“ — amount = suma jednej platby,
  per_months = koľko mesiacov jedna platba pokrýva (mesačne 1, štvrťročne 3, polročne 6; "09/26-01/27" = 5),
  first_due = splatnosť prvej. Bez harmonogramu null.
- advance_payments: z tabuľky „Prehľad preddavkových platieb za fakturačné obdobie“ každá UHRADENÁ záloha
  (date = dátum vyrovnania alebo splatnosť, amount = výška s DPH). Bez tabuľky prázdne pole.
- Pri zálohovom predpise (rozpis záloh) daj kind "zalohova", total = mesačná záloha a period_from/period_to
  = obdobie, na ktoré platí.
- matched_service_id / matched_place_id: id zo zoznamu známych služieb/miest, ktorému dokument patrí
  (rovnaký identifikátor, dodávateľ, adresa odberného miesta). Ak si si istý menej ako na 60 %, daj null
  a match_confidence pod 0.6. Pri účtenke skús odhadnúť miesto z adresy obchodu alebo poznámky, inak null.
- place_hint: adresa odberného miesta („Miesto spotreby“, „Location“) alebo iný text, ktorý prezrádza miesto.
- summary: jedna slovenská veta pre používateľa, napr. "ZSE, vyúčtovanie elektriny 1.9.2025–31.8.2026,
  1 873,37 € (nedoplatok 579,09 €)" alebo "UPC, internet 10/2026–3/2027, 89,70 €".
"""

def _image_block(path: Path, mime: str) -> dict:
    import warnings
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    with Image.open(path) as im:
        # header only so far — refuse huge images before a single pixel is decoded
        if im.width * im.height > MAX_IMAGE_PIXELS:
            raise ExtractError("Fotka je priveľká (viac ako 25 megapixelov). Zmenši ju a nahraj znova.")
        im.draft("RGB", (MAX_IMAGE_SIDE * 2, MAX_IMAGE_SIDE * 2))
        im.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=86, optimize=True)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(buf.getvalue()).decode()}}


def _document_block(path: Path, mime: str) -> dict:
    if mime == "application/pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode()
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    return _image_block(path, mime)


def context_text(places: list[dict], services: list[dict]) -> str:
    lines = ["Známe miesta:"]
    for p in places:
        lines.append(f"- place_id={p['id']}: {p['name']} ({p['kind']}){', ' + p['address'] if p.get('address') else ''}")
    lines.append("Známe služby:")
    for s in services:
        ident = ", ".join(x for x in (s.get("identifier"), s.get("identifier2")) if x)
        lines.append(f"- service_id={s['id']}: {s['kind']} – {s.get('supplier') or 'dodávateľ neuvedený'}"
                     f"{' (' + s['label'] + ')' if s.get('label') else ''}, miesto place_id={s['place_id']}"
                     f"{', identifikátory: ' + ident if ident else ''}")
    if len(services) == 0:
        lines.append("- (zatiaľ žiadne)")
    return "\n".join(lines)


def _client():
    import anthropic
    key = settings.get("anthropic_api_key")
    if not key:
        raise ExtractError("Chýba kľúč Claude API (Nastavenia → Čítanie dokumentov).")
    return anthropic.Anthropic(api_key=key, timeout=180.0, max_retries=2)


def extract(path: Path, mime: str, places: list[dict], services: list[dict], hint: str = "") -> dict:
    """Returns the parsed JSON (validated by the API against SCHEMA). Raises ExtractError."""
    import anthropic
    client = _client()
    model = settings.get("claude_model") or "claude-sonnet-5-5"
    user_text = context_text(places, services)
    if hint:
        user_text += f"\n\nPoznámka používateľa: {hint}"
    user_text += "\n\nPrečítaj priložený dokument a vráť JSON."
    content = [_document_block(path, mime), {"type": "text", "text": user_text}]
    kwargs = dict(model=model, max_tokens=16000, system=SYSTEM,
                  messages=[{"role": "user", "content": content}],
                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}, "effort": "medium"})
    try:
        try:
            # Server-side refusal fallback (routes a declined request to another model inside the call).
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        except (TypeError, anthropic.BadRequestError) as exc:
            log.info("fallbacks unsupported here (%s); plain request", type(exc).__name__)
            resp = client.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        raise ExtractError("Claude API odmietlo kľúč (Nastavenia → Čítanie dokumentov).") from None
    except anthropic.RateLimitError:
        raise ExtractError("Claude API: limit požiadaviek, skúsim neskôr.") from None
    except anthropic.APIStatusError as exc:
        log.warning("claude api error %s: %s", exc.status_code, getattr(exc, "message", exc))
        raise ExtractError(f"Claude API vrátilo chybu {exc.status_code}.") from None
    except anthropic.APIConnectionError:
        raise ExtractError("Claude API je nedostupné (sieť).") from None
    if resp.stop_reason == "refusal":
        raise ExtractError("Model dokument odmietol spracovať.")
    if resp.stop_reason == "max_tokens":
        raise ExtractError("Dokument je pridlhý na jedno čítanie.")
    text = next((b.text for b in resp.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except ValueError:
        raise ExtractError("Model nevrátil platný JSON.") from None
    usage = getattr(resp, "usage", None)
    if usage is not None:
        data["_usage"] = {"input": getattr(usage, "input_tokens", 0), "output": getattr(usage, "output_tokens", 0),
                          "model": getattr(resp, "model", model)}
    return data


def test_connection() -> str:
    """Nastavenia → „Otestovať“: a one-token request that proves the key and model work."""
    import anthropic
    client = _client()
    model = settings.get("claude_model") or "claude-sonnet-5-5"
    try:
        resp = client.messages.create(model=model, max_tokens=64, output_config={"effort": "low"},
                                      messages=[{"role": "user", "content": "Odpovedz jedným slovom: OK"}])
    except anthropic.AuthenticationError:
        raise ExtractError("Kľúč je neplatný.") from None
    except anthropic.NotFoundError:
        raise ExtractError(f"Model „{model}“ neexistuje.") from None
    except anthropic.APIStatusError as exc:
        raise ExtractError(f"Claude API vrátilo chybu {exc.status_code}.") from None
    except anthropic.APIConnectionError:
        raise ExtractError("Claude API je nedostupné (sieť).") from None
    return f"Funguje, model {getattr(resp, 'model', model)}."
