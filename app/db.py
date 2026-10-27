"""SQLite access: one thread-local connection (WAL), tiny query helpers, forward-only migrations.

Domain (všetko po slovensky v UI, v DB anglické názvy):
  places        miesta (byt, dom v Belej, …)
  services      služby na mieste: elektrina / plyn / voda / internet / … s dodávateľom a identifikátormi
  documents     nahrané alebo z mailu stiahnuté súbory: faktúra, účtenka, výpis; + výsledok extrakcie
  invoices      faktúry rozparsované z dokumentov (obdobie, spotreba, suma, splatnosť)
  costs         každý výdavok, ktorý sa počíta do nákladov miesta (faktúra, účtenka, prevod z výpisu)
  transactions  riadky bankových výpisov; spárované s faktúrou alebo zaradené pravidlom
  rules         naučené priradenia: protistrana / identifikátor → miesto, služba, kategória
  readings      denná spotreba z konektorov (ZSD 15-min dáta → kWh/deň)
  connector_runs  behy konektorov (kedy, ok, správa)
"""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  email TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL DEFAULT '',
  is_admin INTEGER NOT NULL DEFAULT 0,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1,
  session_version INTEGER NOT NULL DEFAULT 1,
  ntfy_topic TEXT NOT NULL DEFAULT '',
  notify_ntfy INTEGER NOT NULL DEFAULT 1,
  notify_email INTEGER NOT NULL DEFAULT 0,
  seen_changelog TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  last_login_at TEXT
);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS places (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'byt',
  address TEXT NOT NULL DEFAULT '',
  color TEXT NOT NULL DEFAULT '#3b6ea5',
  sort INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS services (
  id INTEGER PRIMARY KEY,
  place_id INTEGER NOT NULL REFERENCES places(id),
  kind TEXT NOT NULL,
  supplier TEXT NOT NULL DEFAULT '',
  label TEXT NOT NULL DEFAULT '',
  identifier TEXT NOT NULL DEFAULT '',
  identifier2 TEXT NOT NULL DEFAULT '',
  unit TEXT NOT NULL DEFAULT '',
  unit_price REAL,
  fixed_monthly REAL,
  monthly_estimate REAL,
  connector TEXT NOT NULL DEFAULT '',
  connector_ref TEXT NOT NULL DEFAULT '',
  connector_ref2 TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_services_place ON services(place_id);
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'auto',
  status TEXT NOT NULL DEFAULT 'new',
  source TEXT NOT NULL DEFAULT 'upload',
  filename TEXT NOT NULL,
  path TEXT NOT NULL,
  mime TEXT NOT NULL,
  size INTEGER NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL,
  mail_key TEXT,
  mail_from TEXT NOT NULL DEFAULT '',
  mail_subject TEXT NOT NULL DEFAULT '',
  received_at TEXT NOT NULL,
  extracted TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_try_at TEXT,
  place_id INTEGER REFERENCES places(id),
  service_id INTEGER REFERENCES services(id),
  review_note TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_sha ON documents(sha256);
CREATE UNIQUE INDEX IF NOT EXISTS idx_documents_mail ON documents(mail_key) WHERE mail_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE TABLE IF NOT EXISTS invoices (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  service_id INTEGER REFERENCES services(id),
  supplier TEXT NOT NULL DEFAULT '',
  number TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'pravidelna',
  issued_at TEXT,
  period_from TEXT,
  period_to TEXT,
  due_at TEXT,
  total REAL NOT NULL DEFAULT 0,
  to_pay REAL,
  advances REAL,
  currency TEXT NOT NULL DEFAULT 'EUR',
  consumption REAL,
  unit TEXT NOT NULL DEFAULT '',
  unit_price REAL,
  variable_symbol TEXT NOT NULL DEFAULT '',
  iban TEXT NOT NULL DEFAULT '',
  paid_at TEXT,
  paid_transaction_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_invoices_service ON invoices(service_id);
CREATE INDEX IF NOT EXISTS idx_invoices_period ON invoices(period_to);
CREATE TABLE IF NOT EXISTS costs (
  id INTEGER PRIMARY KEY,
  place_id INTEGER REFERENCES places(id),
  service_id INTEGER REFERENCES services(id),
  document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE CASCADE,
  transaction_id INTEGER,
  kind TEXT NOT NULL,
  category TEXT NOT NULL DEFAULT '',
  counterparty TEXT NOT NULL DEFAULT '',
  amount REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'EUR',
  date TEXT NOT NULL,
  period_from TEXT,
  period_to TEXT,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_costs_date ON costs(date);
CREATE INDEX IF NOT EXISTS idx_costs_place ON costs(place_id);
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  amount REAL NOT NULL,
  currency TEXT NOT NULL DEFAULT 'EUR',
  counterparty TEXT NOT NULL DEFAULT '',
  counterparty_iban TEXT NOT NULL DEFAULT '',
  variable_symbol TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  fingerprint TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  invoice_id INTEGER REFERENCES invoices(id),
  cost_id INTEGER REFERENCES costs(id),
  rule_id INTEGER,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_transactions_fp ON transactions(fingerprint);
CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY,
  match_kind TEXT NOT NULL,
  pattern TEXT NOT NULL,
  action TEXT NOT NULL DEFAULT 'assign',
  place_id INTEGER REFERENCES places(id),
  service_id INTEGER REFERENCES services(id),
  category TEXT NOT NULL DEFAULT '',
  label TEXT NOT NULL DEFAULT '',
  hits INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_rules_match ON rules(match_kind, pattern);
CREATE TABLE IF NOT EXISTS readings (
  service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  date TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'consumption',
  value REAL NOT NULL,
  intervals INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'zsd',
  updated_at TEXT NOT NULL,
  PRIMARY KEY (service_id, date, kind)
);
CREATE TABLE IF NOT EXISTS connector_runs (
  id INTEGER PRIMARY KEY,
  connector TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER,
  message TEXT NOT NULL DEFAULT '',
  details TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY,
  at TEXT NOT NULL,
  user_id INTEGER,
  action TEXT NOT NULL,
  details TEXT NOT NULL DEFAULT '',
  ip TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS reminders_sent (
  key TEXT PRIMARY KEY,
  sent_at TEXT NOT NULL
);
"""

# Forward-only migrations, applied in order; PRAGMA user_version = len(applied).
MIGRATIONS: list[str] = [
    SCHEMA,
    # 2026-10-27: what a real ZSE / UPC / Starlink bill carries beyond one total — feed-in from the
    # house's PV, the new advance schedule and the advances the vyúčtovanie already lists.
    """
    ALTER TABLE invoices ADD COLUMN generation_kwh REAL;
    ALTER TABLE invoices ADD COLUMN generation_amount REAL;
    ALTER TABLE invoices ADD COLUMN generation_fee REAL;
    ALTER TABLE invoices ADD COLUMN advance_amount REAL;
    ALTER TABLE invoices ADD COLUMN advance_months INTEGER;
    ALTER TABLE invoices ADD COLUMN advance_from TEXT;
    """,
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(config.DB_PATH), timeout=30, check_same_thread=False,
                               isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
        _local.conn = conn
    return conn


def close() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None


def init() -> None:
    conn = connect()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version):
        conn.executescript(sql)
        conn.execute(f"PRAGMA user_version={i + 1}")


@contextmanager
def tx():
    """Explicit write transaction. autocommit mode otherwise, so a raised request never
    leaks a half-open transaction into the next one. Never `await` inside the block."""
    conn = connect()
    if conn.in_transaction:
        yield conn
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def q(sql: str, params=()) -> list[sqlite3.Row]:
    return connect().execute(sql, params).fetchall()


def q1(sql: str, params=()):
    return connect().execute(sql, params).fetchone()


def run(sql: str, params=()) -> int:
    """Execute a write; returns lastrowid. Wrap several in tx() for atomicity."""
    cur = connect().execute(sql, params)
    return cur.lastrowid


def rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def row(r) -> dict | None:
    return dict(r) if r is not None else None


def get_setting(key: str, default: str = "") -> str:
    r = q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r is not None else default


def set_setting(key: str, value: str) -> None:
    run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value))


def log_history(user_id, action: str, details=None, ip: str = "") -> None:
    run("INSERT INTO history(at,user_id,action,details,ip) VALUES(?,?,?,?,?)",
        (now_iso(), user_id, action, json.dumps(details or {}, ensure_ascii=False), ip))
