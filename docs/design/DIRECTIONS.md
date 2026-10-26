# Dizajnové smery (2026-10-26) — na výber

Brief: Jano, jeden človek s tromi domácnosťami (byt v Bratislave, dom v Belej, chalupa), otvára appku
raz za pár dní na mobile, raz za mesiac na desktope. Hlavná otázka domovskej obrazovky: **„Koľko ma
tento mesiac stoja domácnosti, čo je odhad a čo ešte príde?“** Svet témy: elektromer, odpočet, faktúra,
výpis — nie fintech. Primárna akcia: nahrať účet (fotka / PDF). Osobná appka, značka voľná.

Statické náhľady a screenshoty sú v scratchpade session (necommitované). Spoločné pre všetky smery:
mesiac sa prepína v hlavičke, miesta majú stálu farbu, „odhad“ je odlíšený tvarom (prerušovane / ≈ /
kurzíva), nie len farbou; spodná lišta Prehľad · Dokumenty · [Nahrať] · Miesta · Viac.

## A — Elektromer (svetlý, nástrojový)
- Tokeny: pozadie `#f2f3f0` (sivý papier), karta `#fff`, linka `#d9dcd5`, text `#181c1e`, tlmený `#5f6a6b`;
  miesta `#2f6fa8` / `#3f8a5a` / `#c4742a`; stavy ok `#2c7a52`, pozor `#b9731a`. Dark: `#181b1d` / `#202427`.
- Písmo: **Manrope** (jedna rodina, tabulkové číslice), sumy s rozstupom 0.04–0.06 em ako na počítadle.
- Rozloženie: suma mesiaca ako počítadlo + 12 mesačných stĺpcov, pod tým pilulky „čaká na teba“, „Splatné“,
  potom karty miest. Desktop: ľavý stĺpec (suma, splatné) + mriežka miest.
- Signature: **farebná páska** na ľavej hrane každého miesta (ako značenie potrubí) a číslice počítadla.
- Zaoblenie 6 px, kompaktné.

## B — Domy (teplý, farebné bloky)
- Tokeny: pozadie `#efe9df`, karta `#fbf8f2`, linka `#ddd4c4`, text `#23201b`; miesta ako plné bloky
  `#3461a8` / `#2f7d4f` / `#b5572a` s bielym textom. Dark: `#1b1916` / `#262320`.
- Písmo: **Bricolage Grotesque** (opsz os: display pre sumy, text pre riadky), tabulkové číslice.
- Rozloženie: obrovská suma + jedna veta („Tri domácnosti. Podľa faktúr…“), potom tri farebné „domy“, v každom
  biely zoznam služieb; splatné na konci. Desktop: tri domy vedľa seba.
- Signature: **miesta ako farebné domy** so sparkline spotreby priamo v bloku.
- Zaoblenie 20 px, vzdušné. Riziko: krémový podklad patrí k „AI“ defaultom — pri výbere B zmeniť
  papier na chladnejší kartón (`#e8e6e1`) a odstrániť dekoračný kruh v rohu blokov.

## C — Velín (tmavý, dátový)
- Tokeny: pozadie `#171c22`, karta `#1f252c`, linka `#313a44`, text `#e9edf1`, tlmený `#8e9aa6`;
  miesta `#5fa8f5` / `#5fcf8d` / `#f0a35c`; pozor `#f0c24a`. Light: `#e8ebee` / `#f6f7f8`.
- Písmo: **Instrument Sans** (text) + **Azeret Mono** (čísla) — dve jasne rôzne rodiny.
- Rozloženie: prepínač Týždeň/Mesiac/Rok, 2 KPI karty, **stĺpcový graf elektriny po dňoch** (stacked po miestach),
  tabuľka Miesto/Služba · Spotreba · € a posledné dokumenty. Desktop: dva stĺpce.
- Signature: denný graf spotreby všetkých domov na domovskej obrazovke.
- Zaoblenie 10 px, hustá tabuľka. Riziko: mono čiarka v sumách („412 , 80“) — pri výbere C desatiny v Instrument Sans.

## Sebakritika (zoznam zlozvykov, design.md § 5)
- A: 12 stĺpcov bez hodnôt je dekorácia, kým nie sú klikateľné (→ klik = prepnutie mesiaca). Inak čisté.
- B: krémová + terakota (viď vyššie); kruh v rohu blokov = dekorácia bez funkcie → preč.
- C: tri rovnaké KPI karty = „mriežka dlaždíc“; pilulky upozornení duplikujú stavy v tabuľke → nechať len pilulky.

## Design Council (panel urobený v session náhradou za skill — hodnotenie 1–5)
| Smer | Ive (materiál) | Rams (ekonómia) | Hadid (pohyb) | Ingels (radosť) | Norman (zrozumiteľnosť) |
|---|---|---|---|---|---|
| A Elektromer | 4 — papier a páska sú čestné; prerušovaný podčiark = odhad bez farby | 4 — málo prvkov, stĺpce bez čísel treba oživiť | 3 — statická mriežka, bez rytmu | 3 — páska a počítadlo sú jediný vtip | 4 — jasné; legenda „prerušované = odhad“ raz na začiatku |
| B Domy | 3 — bloky ako natreté domy, ale krém = videné | 3 — dekoračný kruh, dve veľkosti súm navyše | 4 — suma → veta → domy = najlepší tok | 5 — „takmer nič, iba internet a svetlo“, farby bývania | 3 — kurzíva+~ pre odhad je slabé; biely text na oranžovej treba overiť (AA) |
| C Velín | 3 — mono číslice sedia na prístroj, čiarka nie | 3 — najviac prvkov (KPI + graf + pilulky + 2 tabuľky) | 2 — rovnaké karty pod sebou | 4 — graf „domy dýchajú“ je ski slope | 4 — ≈ je medzinárodné, tabuľka sa číta rýchlo |

Napätie Rams × Ingels: A je najtichšie, B najhravejšie. Riešenie: **A ako základ + z C denný graf elektriny
(klikateľný, v karte Belá a v detaile služby) + z B jedna veta pod sumou**. Ak má appka mať viac charakteru,
B s chladnejším papierom.
