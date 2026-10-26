# Dizajn Nakladiaku — smer „Domy“ s chladným podkladom (vybrané 2026-10-26)

Brief: Jano, tri domácnosti (byt v Bratislave, dom v Belej, chalupa), otvára appku raz za pár dní na
mobile, raz za mesiac na desktope. Domovská obrazovka odpovedá na: **„Koľko ma tento mesiac stoja
domácnosti, čo je odhad a čo ešte príde?“** Primárna akcia: nahrať účet (fotka / PDF).

## Tokeny
```css
:root {
  --bg: #e9e8e3;        /* chladný kartón, nie krém */
  --panel: #f7f6f2;     /* biely list v bloku, karty, sheety */
  --line: #d4d2ca;
  --text: #1f1e1b;      /* atrament */
  --muted: #6a675f;
  --ink: #1f1e1b;       /* primárne tlačidlo, aktívna záložka */
  --accent: #b5572a;    /* jediná akcentová farba: tlačidlo Nahrať účet, čaká-na-teba */
  --ok: #2f7d4f;  --warn: #9a6a12;  --err: #b3362a;
  --byt: #3461a8; --dom: #2f7d4f; --chalupa: #b5572a;   /* default farby miest; každé miesto má --c */
  --font: "Bricolage Grotesque", system-ui, -apple-system, "Segoe UI", sans-serif;
  --r: 20px; --r-sm: 12px;
}
dark: --bg #1a1a18, --panel #262521, --line #3a3833, --text #f1efe8, --muted #a39e92, --ink #f1efe8 (na tmavom je „atrament“ svetlý).
```
- **Písmo:** Bricolage Grotesque (OFL, self-host `app/static/fonts/BricolageGrotesque.ttf`, variabilné opsz/wdth/wght).
  Sumy a nadpisy `font-variation-settings: "opsz" 96`, text default. Všade `font-feature-settings: "tnum"`.
- **Škála:** 58/84 px hero suma · 40 px suma miesta · 20 px nadpis bloku · 17 px text · 14 px pomocný · 12 px drobný.
- **Zaoblenie:** bloky a sheety 20 px, vnútorné listy 16 px, tlačidlá pilulky 999 px, inputy 12 px.

## Signature
**Miesta ako farebné domy**: každé miesto je plný farebný blok (`--c`) s bielym textom, v ňom „biely list“ so
službami. Sparkline spotreby (ZSD) priamo v bloku. Nič iné na obrazovke nie je farebné okrem jedného
oranžového tlačidla „Nahrať účet“ a stavov.

## Čo robíme
- Hero = suma mesiaca + jedna veta („Tri domácnosti. Podľa faktúr 298,10 €, odhad ďalších 114,70 €. Oproti septembru o 6 % menej.“).
- Odhad je označený `≈` pred sumou a tlmenou farbou (tvar, nie len farba). Faktúra = plná suma.
- Stavové pilulky „čaká na teba“: atramentová pilulka s číslom; sekundárne obrysové.
- Spodná lišta = pilulky Prehľad · Dokumenty · [+ Nahrať účet] · Miesta; Nastavenia a Profil cez avatar vpravo hore.
- Sheets zdola (20 px), na desktope dialóg v strede. Toast dole nad lištou.
- Prázdne stavy jednou vetou + tlačidlo na prvý krok.

## Čo nerobíme
- Žiadne dekoračné kruhy v blokoch (vyhodené po sebakritike), žiadne tiene pod každou kartou, žiadne gradienty.
- Žiadne emoji ako ikony; ikony inline SVG z jednej sady (Lucide-like, stroke 2).
- Žiadne verzálkové eyebrow štítky, žiadne „→“ za tlačidlami.
- Krém `#efe9df` nie — podklad je chladný kartón.
