# Nakladiak

Všetky pravidelné náklady domácností na jednom mieste: byt, dom v Belej, chalupa — elektrina, plyn,
voda, internet, Starlink, správca, záhradník, upratovanie. Beží na **https://nak.gordulic.sk**.

## Čo appka robí

- **Nahraješ účet, zvyšok spraví sama.** PDF alebo fotka faktúry, účtenky či výpisu z účtu (aj rovno
  z fotoaparátu). Appka prečíta dodávateľa, obdobie, spotrebu, sumu a splatnosť a priradí dokument
  k miestu a službe. Keď si nie je istá, opýta sa raz; so zaškrtnutým „Zapamätať si to“ pôjde ďalší
  dokument od rovnakého dodávateľa alebo obchodu bez pýtania.
- **Schránka na účty.** Maily od dodávateľov presmeruj do vyhradenej schránky; appka ju číta každých
  15 minút a prílohy spracuje sama. Z mailu sa zaúčtuje bez pýtania len faktúra s poznaným identifikátorom
  (EIC, POD, číslo zmluvy) alebo naučeným pravidlom; ostatné čakajú na potvrdenie. V Nastaveniach → Schránka
  môžeš určiť dôveryhodných odosielateľov.
- **Výpis z účtu.** Platby sa spárujú s faktúrami (faktúra je potom „zaplatená“). Neznáme platby
  (záhradník, správca, upratovanie) zaradíš raz k miestu a kategórii, ďalšie od rovnakej protistrany
  sa zarátajú samy. Každých 30 dní príde pripomienka „nahraj výpis“.
- **ZSD 15-minútové dáta.** Denná spotreba elektriny (aj dodávka do siete) pre všetky odberné miesta
  jedného konta z diportal.sk. V prehľade je odhad ceny do konca mesiaca podľa priebežnej spotreby.
- **Prehľad.** Suma mesiaca, jedna veta (podľa faktúr vs. odhad, porovnanie s minulým mesiacom),
  farebné bloky miest so službami, splatné faktúry, 12 mesiacov histórie. Mesiace sa prepínajú šípkami.
- **Upozornenia** cez ntfy: spracovaný dokument, dokument na potvrdenie, faktúra pred splatnosťou,
  týždenná spotreba, pripomienka na výpis, chyba sťahovania.

## Prvé kroky

1. Prihlás sa ako `jano` s heslom z `.env` (jediná vec v `.env`; prihlásenie vydrží 30 dní).
2. **Miesta** → Pridať miesto (byt, dom, chalupa). Pri každom **Pridať** službu: druh, dodávateľ,
   identifikátor z faktúry (EIC, POD, číslo zmluvy) — podľa neho sa faktúry priraďujú samy.
3. **Nastavenia → Čítanie**: kľúč Claude API, „Otestovať spojenie“.
4. **Nahrať účet** — prvú faktúru. Ak sa appka opýta, potvrď miesto a službu.
5. Voliteľne **Nastavenia → Schránka** (IMAP) a **Zdroje dát** (ZSD prihlásenie, business partner,
   2captcha kľúč; po prvom stiahnutí priraď odberné miesta k službám cez Upraviť službu → Zdroj dát).
6. **Profil**: ntfy téma a skúšobná notifikácia; na mobile Zdieľať → Pridať na plochu.

## Ako sa počítajú náklady

- **Faktúra za obdobie** (mesačná, štvrťročná, polročná — UPC, O2, Starlink) → rozpočíta sa rovnomerne
  na mesiace obdobia (UPC 89,70 € za polrok = 6 × 14,95 €), aby história nemala skoky a žiadny mesiac
  nedostal k faktúre ešte aj odhad. Dobropis znižuje náklady.
- **Ročné vyúčtovanie** (ZSE, SPP, voda) → do nákladov ide len nedoplatok (preplatok záporne), zálohy sa
  počítajú mesačne. Uhradené zálohy, ktoré vyúčtovanie samo vypisuje, appka doplní za mesiace, kde ich ešte
  nemá z výpisu; keď príde výpis neskôr, platba sa priradí k tej istej položke. Nová výška zálohy
  z harmonogramu sa stane odhadom na ďalšie mesiace. Pri dome s fotovoltikou (ZSE: faktúra za spotrebu +
  faktúry za výrobu + sumarizácia v jednom PDF) sa účtuje suma zo sumarizácie a dodávka do siete sa eviduje
  pri faktúre.
- **Zálohový predpis** (rozpis záloh) → nič do nákladov, len odhad na mesiac a nič „na úhradu“.
- **Služba bez faktúry v mesiaci**: odhad = spotreba × cena za jednotku + fixný poplatok (pri ZSD dátach),
  inak mesačná záloha / paušál. Odhad je v prehľade označený `≈`.
- **Účtenka** → položka nákladov miesta v kategórii (údržba, nákup…).
- **Platba z výpisu** → položka nákladov, ak nie je platbou známej faktúry (rovnaký VS a suma) ani pravidelnej
  faktúry tej služby v okolí ±45 dní. Platba okolo vyúčtovania je záloha, teda náklad.

## Lokálny vývoj

```bash
python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
DATA_DIR=./data ADMIN_PASSWORD=testheslo123 APP_URL=http://127.0.0.1:8180 uvicorn app.main:app --port 8180 --reload
pytest -q
```

Ďalšie: `DEPLOY.md` (VPS), `CLAUDE.md` (konvencie), `changelog.md` (čo je nové), `docs/design/DESIGN.md`.
