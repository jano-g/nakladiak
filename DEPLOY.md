# Deploy — Nakladiak (nak.gordulic.sk)

Cieľ: VPS `niko1` (Ubuntu, Docker + compose, nginx + certbot už bežia). Rovnaký vzor ako `kal`, `img`:
stack v `/opt/nakladiak`, kontajner iba na `127.0.0.1:8180`, nginx robí HTTPS cez `picus/infra/new-site.sh`.

## 1. DNS
Na websupport.sk pridaj `A` záznam `nak.gordulic.sk` → `5.22.220.32`. Over `dig +short nak.gordulic.sk`
(bez záznamu `new-site.sh` zastaví s chybou DNS).

## 2. Klon a konfigurácia
```bash
git clone git@github.com:jano-g/nakladiak.git /opt/nakladiak
```
```bash
cd /opt/nakladiak && cp .env.example .env && chmod 600 .env && nano .env
```
V `.env` vyplň aspoň:
- `APP_URL=https://nak.gordulic.sk` (už je), `APP_PORT=8180`, `APP_BIND=127.0.0.1` (nechaj)
- `ADMIN_USERNAME`, `ADMIN_NAME`, `ADMIN_EMAIL`, **`ADMIN_PASSWORD` aspoň 8 znakov** — použije sa len pri prvom štarte
- `SECRET_KEY` nechaj prázdny (vygeneruje sa do `/data/secret.key`, deploy nikoho neodhlási)
- `ALERT_NTFY_TOPIC` — hodnota z `/etc/web-healthcheck.env` (chyby appky na ntfy)
- `ANTHROPIC_API_KEY`, IMAP, ZSD a SMTP môžeš vyplniť aj neskôr v appke (Nastavenia); hodnoty z `.env` sú základ, DB vyhráva.

## 3. Štart
```bash
cd /opt/nakladiak && docker compose up -d --build
```
```bash
docker logs nakladiak --tail 20
```
```bash
curl -s http://127.0.0.1:8180/healthz
```
Očakávané: `Nakladiak started` + `Uvicorn running`, healthz `{"ok":true}` (po ~10 s, kým naskočí scheduler).
Obraz je `mcr.microsoft.com/playwright/python:v1.64.0-noble` (Chromium pre ZSD) — prvý build stiahne ~1,5 GB.
Dáta: volume `nakladiak_nakladiak_data` (`/data`: `nakladiak.db`, `docs/` nahrané súbory, `secret.key`).

## 4. nginx + HTTPS
```bash
cd /opt/picus && git pull
```
```bash
sudo /opt/picus/infra/new-site.sh /opt/nakladiak
```
Skript zoberie doménu z `APP_URL`, port z compose, `client_max_body_size 30m` a `proxy_read_timeout 120s`
z `docs/nginx/nak.gordulic.sk.conf`, vypýta certifikát (`certbot certonly`), vygeneruje vhost, `nginx -t`, reload.
Over: `curl -sI https://nak.gordulic.sk/ | head -1` → `HTTP/2 303` (presmerovanie na /login), `/healthz` → 200.

## 5. Prvé spustenie v prehliadači
1. https://nak.gordulic.sk → prihlásenie admina.
2. **Nastavenia → Čítanie**: kľúč Claude API → „Otestovať spojenie“.
3. **Nastavenia → Notifikácie**: „Poslať skúšobnú notifikáciu“ (téma chýb). **Profil**: vlastná ntfy téma + skúšobná.
4. **Miesta**: pridaj byt / dom / chalupu a k nim služby (dodávateľ + identifikátor z faktúry).
5. **Nahrať účet**: prvá faktúra; potvrď priradenie, ak sa appka opýta.
6. **Nastavenia → Schránka**: IMAP schránky na účty → „Otestovať prihlásenie“ → „Prečítať schránku teraz“.
7. **Nastavenia → Zdroje dát**: ZSD prihlásenie, business partner ID (ako v `spotreba_bela/.env`), 2captcha kľúč
   → „Stiahnuť teraz“. Potom pri každej elektrine v Belej: Upraviť službu → Zdroj dát ZSD → vybrať odberné miesto.
   `spotreba_bela` nechaj bežať, kým týždenný prehľad z nakladiaku neoveríš (pondelok ráno na ntfy).
8. **Nastavenia → O appke**: „nasadené“ = čas buildu, „Čo je nové“ = `changelog.md`.
9. Mobil: Zdieľať → Pridať na plochu.

## 6. Aktualizácia
```bash
cd /opt/nakladiak && git pull && docker compose up -d --build
```
`.env` a `/data` zostávajú. Po deployi ostaneš prihlásený (kľúč v `/data/secret.key`).

## 7. Zálohy a obnova
- **VPS restic → B2** (`picus/infra/backup.sh`): riadok
  `dump_sqlite_container nakladiak nakladiak.db nakladiak` + riadok `nakladiak|/opt/nakladiak|nakladiak|sqlite-vol|nakladiak|nakladiak.db|`
  v `infra/restore-app.sh` (už pripravené v picus). `.env` zachytí existujúci krok.
- **Nahrané PDF/fotky (`/data/docs`) sa nezálohujú** — rozhodnutie 2026-10-26: dajú sa nahrať znova, DB
  obsahuje všetko prečítané. Zálohuje sa len DB (vrátane kľúčov zadaných v Nastaveniach — dump je citlivý ako `.env`).
- Po nasadení spusti zálohu ručne: `sudo systemctl start restic-backup.service` a over `ok nakladiak` v logu.
- Obnova: `sudo /opt/picus/infra/restore-app.sh nakladiak`. Nikdy nekopíruj `.db` do bežiaceho kontajnera.

## 8. Údržba
| Čo | Ako |
|---|---|
| Zabudnuté heslo | „Zabudol som heslo“ na /login (ak je SMTP); inak `docker compose exec nakladiak python -m app.cli set-password jano` |
| Používatelia | `docker compose exec nakladiak python -m app.cli users` |
| ZSD ručne / viac dní | `docker compose exec nakladiak python -m app.cli zsd --days 30` |
| Schránka ručne | `docker compose exec nakladiak python -m app.cli imap` |
| Prečítať dokument znova | v appke „Prečítať znova“, alebo `python -m app.cli process <id>` |
| Logy | `docker logs nakladiak --tail 100 -f` |
| Health | `curl -s http://127.0.0.1:8180/healthz` (503 = DB alebo scheduler; kontroluje aj web-healthcheck) |
| Pamäť | `docker stats nakladiak` počas ZSD behu; limit 768m v compose — po týždni skontroluj špičku a prípadne zníž |

## Troubleshooting
| Symptóm | Príčina / riešenie |
|---|---|
| `env file /opt/nakladiak/.env not found` | krok 2 |
| Kontajner padá s „ADMIN_USERNAME a ADMIN_PASSWORD (aspoň 8 znakov)“ | doplň admina v `.env`, `docker compose up -d` |
| Login vždy odmietnutý | heslo z `.env` platí len pri prvom štarte; `app.cli set-password` |
| Dokument ostáva „čaká v rade“ / chyba „Chýba kľúč Claude API“ | Nastavenia → Čítanie, kľúč + test |
| Dokument „chyba“ 4× | otvor ho, „Prečítať znova“ s poznámkou; limit API alebo nečitateľný sken |
| Upload „413“ alebo nič sa nedeje | nginx `client_max_body_size` (30m vo vhoste) |
| Schránka: chyba prihlásenia | websupport IMAP `imap.m1.websupport.sk:993`, meno = celá adresa |
| ZSD: „Login failed“ / 2captcha timeout | heslo na diportáli, kredit na 2captcha; `docker logs` ukáže `[zsd]` riadky; 2 zlyhania po sebe = ntfy |
| ZSD: OOM / kontajner reštartuje počas behu | `docker stats`; zvýš `mem_limit` (Chromium ~560 MB špička) |
| Po deployi sú všetci odhlásení | `SECRET_KEY` sa mení alebo volume chýba — nechaj prázdny, over volume |
| Chyby appky nechodia na ntfy | `ALERT_NTFY_TOPIC` v `.env` alebo Nastavenia → Notifikácie, skúšobná |
| `new-site.sh`: „publishes port(s) … on ALL interfaces“ | `APP_BIND=127.0.0.1` |
| `new-site.sh`: „already exists“ | vhost už je — uprav ručne + `sudo nginx -t` |
| 502 z nginx | `docker ps`; port 8180 v `.env` aj vo vhoste rovnaký |
