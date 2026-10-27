# Čo je nové

## 2026-10-27
- **Čítanie podľa skutočných účtov** — prompt a schéma vyladené na Starlink (anglická faktúra), UPC (polročná
  faktúra), ZSE vyúčtovania bytu (nedoplatok aj preplatok) a balík ZSE pre dom s fotovoltikou (spotreba +
  výroba + sumarizácia). Dodávateľ sa zapisuje značkou (ZSE, nie Energetika Slovensko), zákaznícke číslo
  spoločné pre všetky odbery sa nepoužíva na priradenie.
- **Faktúra za viac mesiacov sa rozpočíta** rovnomerne na mesiace obdobia; polročný UPC už nie je jeden
  skok v októbri plus odhad v ďalších mesiacoch.
- **Vyúčtovanie účtuje len nedoplatok (preplatok záporne)** a doplní uhradené zálohy, ktoré samo vypisuje,
  za mesiace bez výpisu. Výpis nahraný neskôr sa k nim priradí, nič sa nepočíta dvakrát. Nová záloha
  z harmonogramu (mesačná, štvrťročná, polročná) je odhad na ďalšie mesiace; zálohový predpis už nie je
  „splatná faktúra“.
- **Dodávka do siete** z faktúry za výrobu (kWh, suma, poplatok) je v detaile dokumentu.
- Variabilný symbol z prvej priradenej faktúry sa uloží ako druhý identifikátor služby (UPC → O2 od 11/2026
  mení názov, VS ostáva). Opätovné čítanie zaplatenej faktúry už nepadá.

## 2026-10-26 (prvá verzia)
- **Miesta a služby** — byt, dom v Belej, chalupa… a pri každom elektrina, plyn, voda, internet a ďalšie služby s dodávateľom a identifikátormi.
- **Nahraj účet, zvyšok spraví appka** — PDF alebo fotka účtu, účtenky či výpisu; appka prečíta dodávateľa, obdobie, spotrebu a sumu a priradí ich k miestu. Keď si nie je istá, opýta sa raz a nabudúce to už vie.
- **Schránka na účty** — maily od dodávateľov presmeruj do vyhradenej schránky, appka ju číta každých 15 minút.
- **Výpis z účtu** — platby záhradníkovi, správcovi či upratovanie zaradíš raz, potom sa zarátavajú samy. Platby za faktúry sa spárujú a faktúra je označená ako zaplatená.
- **ZSD 15-minútové dáta** — denná spotreba (aj dodávka do siete) pre všetky odberné miesta z diportal.sk.
- **Prehľad** — mesačné náklady po miestach a službách, odhad do konca mesiaca podľa priebežnej spotreby, splatné faktúry, história 12 mesiacov.
- **Upozornenia** — nový spracovaný dokument, faktúra pred splatnosťou, týždenná spotreba a pripomienka na výpis cez ntfy.
