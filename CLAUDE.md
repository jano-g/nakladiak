# Nakladiak

Náklady domácností (byt, dom v Belej, chalupa) na nak.gordulic.sk (nástupca spotreba_bela, odstránenej 2026-10-26): nahraj faktúru / účtenku / výpis,
Claude ju prečíta, appka priradí k miestu a službe (keď si nie je istá, opýta sa raz a zapamätá si to),
výpis spáruje s faktúrami, ZSD diportal dodáva dennú spotrebu elektriny. Prehľad = suma mesiaca po miestach.

> Infra a deploy: picus `PICUS.md` (B29). Kroky: `DEPLOY.md`. Vzhľad: `docs/design/DESIGN.md` (smer „Domy“).

## Stack (keep it this simple)
- Python 3.12 + FastAPI, SQLite (WAL) `/data/nakladiak.db`, súbory `/data/docs/`, Jinja len login/akčné stránky,
  inak SPA `app/static/js/app.js` (vanilla, `el()` — nikdy `innerHTML` s dátami) + `app/static/css/app.css`.
  Žiadny build step, ORM ani Redis. Obraz = Playwright image (Chromium pre ZSD).
- Jeden uvicorn proces; `app/scheduler.py` (thread, tick 30 s): čítanie dokumentov (jeden naraz, zámok),
  IMAP každých 15 min, ZSD denne o `zsd_time`, pripomienky, upratovanie. Ťažké joby pod jedným zámkom `_heavy`.
- Doména: `services/documents.py` (uloženie, pipeline, matching, review), `services/extract.py` (Claude,
  štruktúrovaný výstup `SCHEMA`), `services/bank.py` (výpisy, pravidlá, párovanie faktúr), `services/costs.py`
  (dashboard, odhady), `services/mailbox.py` (IMAP), `connectors/zsd.py` + `zsd_fetch.py` (subprocess, Playwright).
- `.env` je základ, `settings.OVERRIDABLE` prepísateľné v Nastaveniach (DB vyhráva); `SECRET_KEYS` sa nevracajú do UI.

## Konvencie
- UI po slovensky, krátko, druhá osoba; mená neskloňuj. Odhad = `≈` + tlmená farba, faktúra = plná suma.
- Každá zápisová API cesta: `X-Requested-With: nakladiak` (CSRF), `current_user()` / `admin_user()`, `db.tx()`,
  `db.log_history()`. Slovenská hláška cez `ApiError` ide rovno do toastu.
- Dokument: `new → processing → done | needs_review | error` (backoff 5/30/180/720 min, po 4. pokuse alert).
  `apply()` je idempotentné (maže a znova vkladá invoices/costs daného dokumentu). Výstup modelu je dátový
  vstup, nie pravda: služba sa priraďuje najprv identifikátorom / pravidlom, model až pri istote ≥ 0.8.
- Náklady sa nikdy nepočítajú dvakrát: platba z výpisu k faktúre = `transactions.status='invoice'`, bez cost riadku.
- Nová funkcia = API + UI + text notifikácie + riadok v `changelog.md` naraz; testy v `tests/` (`pytest`),
  Claude sa v testoch mockuje (`monkeypatch extract.extract`).
- Zápisy do cudzích systémov neexistujú (len čítanie: Claude, IMAP, diportal). Credentials ZSD idú do subprocesu
  cez stdin, nikdy cez argv.

## Lokálny vývoj
```bash
cp .env.example .env    # ADMIN_PASSWORD aspoň 8 znakov
DATA_DIR=./data ADMIN_USERNAME=jano ADMIN_PASSWORD=testheslo123 APP_URL=http://127.0.0.1:8180 uvicorn app.main:app --port 8180 --reload
pytest -q               # 37+ testov, izolovaná DB v tmp
```
Screenshoty: `scripts/screenshots.py` zo skillu appka-builder (Chromium `/opt/pw-browsers/chromium`).

## Deploy (VPS niko1)
`/opt/nakladiak`, kontajner `127.0.0.1:8180`; vhost + cert `sudo /opt/picus/infra/new-site.sh /opt/nakladiak`;
update `git pull && docker compose up -d --build`. Secrets `/opt/nakladiak/.env` (0600). Zálohy: restic riadok
v `picus/infra/backup.sh` (len DB; `/data/docs` sa nezálohuje — rozhodnutie).

## Gotchas
- Behind nginx: rate limiter berie **posledný** hop `X-Forwarded-For`; uvicorn bez `--proxy-headers`.
- `playwright==` v requirements musí sedieť s tagom Playwright image v Dockerfile (test to pinuje).
- ZSD beh: Chromium ~560 MB špička → `mem_limit 768m`; `init: true` kvôli zombie procesom.
- Statika má `?v=` (`templating.ASSET_VERSION`) — pri zmene CSS/JS zvýš verziu; SW cachuje len `/static/`.
- V JS: `mount()` filtruje `null` deti; custom property cez `style.setProperty`; jediný `innerHTML` je `ICONS`.
