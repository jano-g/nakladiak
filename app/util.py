"""Slovak date/number formatting, local-time helpers (all wall-clock math in APP_TZ) and
input cleaning."""
import re
import unicodedata
from datetime import date, datetime, timedelta

from . import config

# C0/C1 controls and the bidi overrides. Control characters in a name end up in an e-mail
# Subject (header injection) or an ntfy title; the bidi ones let text render in an order
# the author did not write.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f‎‏‪-‮⁦-⁩]")


def clean_text(value, max_len: int, *, multiline: bool = False) -> str:
    s = unicodedata.normalize("NFC", str(value or ""))
    s = _CONTROL.sub("", s)
    if multiline:
        s = s.replace("\r\n", "\n").replace("\r", "\n")
        s = re.sub(r"\n{3,}", "\n\n", s)
    else:
        s = s.replace("\n", " ").replace("\r", " ")
        s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()[:max_len]


def fold(text) -> str:
    """Lower-case, strip diacritics and collapse whitespace — for matching names/identifiers."""
    s = unicodedata.normalize("NFKD", str(text or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s.lower()).strip()


def norm_identifier(text) -> str:
    """EIC/POD/VS/IBAN as the supplier prints it vs. as the user typed it: keep only [A-Z0-9]."""
    return re.sub(r"[^A-Z0-9]", "", str(text or "").upper())


SK_DAYS = ["pondelok", "utorok", "streda", "štvrtok", "piatok", "sobota", "nedeľa"]
SK_DAYS_SHORT = ["Po", "Ut", "St", "Št", "Pi", "So", "Ne"]
SK_MONTHS = ["január", "február", "marec", "apríl", "máj", "jún", "júl", "august",
             "september", "október", "november", "december"]
SK_MONTHS_GEN = ["januára", "februára", "marca", "apríla", "mája", "júna", "júla", "augusta",
                 "septembra", "októbra", "novembra", "decembra"]


def now_local() -> datetime:
    return datetime.now(config.TZ)


def today_local() -> date:
    return now_local().date()


def parse_date(s) -> date | None:
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return nxt - timedelta(days=1)


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, 1)


def fmt_date(d: date, with_weekday: bool = False) -> str:
    s = f"{d.day}. {SK_MONTHS_GEN[d.month - 1]}"
    if d.year != today_local().year:
        s += f" {d.year}"
    return f"{SK_DAYS[d.weekday()]} {s}" if with_weekday else s


def fmt_month(ym: str) -> str:
    y, m = ym.split("-")[:2]
    return f"{SK_MONTHS[int(m) - 1]} {y}"


def fmt_dt(iso: str) -> str:
    """ISO UTC -> 'st 3. septembra 14:05' in local time."""
    try:
        dt = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    local = dt.astimezone(config.TZ)
    return f"{SK_DAYS_SHORT[local.weekday()].lower()} {local.day}. {SK_MONTHS_GEN[local.month - 1]} {local:%H:%M}"


def fmt_eur(x) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return f"{s} €"


def plural(n: int, one: str, few: str, many: str) -> str:
    if n == 1:
        return f"{n} {one}"
    if 2 <= n <= 4:
        return f"{n} {few}"
    return f"{n} {many}"


def to_float(v, default=None):
    if v is None or v == "":
        return default
    try:
        if isinstance(v, str):
            v = v.replace(" ", "").replace(" ", "").replace(",", ".")
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):
        return default
    return f
