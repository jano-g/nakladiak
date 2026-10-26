# Rešerš — náklady domácností, energie, účty (2026-10-26)

Kategória: osobný finančný/energetický prehľad pre jedného človeka s viacerými domácnosťami.
Pozreté verejné stránky a (z pamäte) produktové obrazovky; screenshoty sú len v scratchpade, necommitujú sa.

| Referencia | Čo berieme | Čo nie a prečo |
|---|---|---|
| Tibber (app) — https://tibber.com | Spotreba ako denné stĺpce s cenou pod nimi; kWh a € vedľa seba, nie na dvoch obrazovkách; tmavá téma funguje pre „velín“ | marketingová fotografická estetika; hravý tón značky |
| Octopus Energy (app) — https://octopus.energy/app/ | Graf spotreby za deň/týždeň/mesiac s prepínačom období na jednom mieste; „čo ma to stojí dnes“ ako prvá veta | fialovo-ružová brand paleta, maskot |
| Home Assistant Energy — https://www.home-assistant.io/dashboards/energy/ | Výber obdobia (deň ◀ ▶, „Teraz“) v hlavičke, porovnanie s predošlým obdobím; stacked bary po zdrojoch | technický vzhľad, priveľa kariet rovnakej váhy |
| Sense / Emporia — https://sense.com, https://www.emporiaenergy.com | Jeden hlavný údaj (odber teraz / dnes) + rozpad; oranžová ako „živá“ energia | hardvérové landing pages, nič pre nás z layoutu |
| Monarch Money — https://www.monarchmoney.com | Karta „Budget · Actual · Remaining“ = presne náš „Záloha · Skutočnosť · Odhad“; serif len na nadpisy, čísla sans | oranžové CTA, foto hero |
| Copilot Money — https://copilot.money | Kategórie ako farebné „pilulky“ s vlastnou farbou; tmavý modrošedý podklad, nie čierny | rozmazané 3D efekty, každá kategória inou krikľavou farbou |
| YNAB — https://www.ynab.com | Účtovnícka tabuľka: zarovnané stĺpce, tabulkové číslice; peniaze sa čítajú v riadkoch | hustý nástroj na každodenné rozpočtovanie, my sme „raz za týždeň pozrieť“ |
| Rocket Money — https://rocketmoney.com | Zoznam pravidelných platieb s dátumom ďalšej platby a logom dodávateľa; „čo platíš a nepoužívaš“ je presne iterácia 2 | predajný tón, upsell |
| Lunch Money — https://lunchmoney.app | Priateľský, nenásilný tón, žltá mince-ikona; svetlý podklad s jemným vzorom | vzor na pozadí ruší čísla |
| Spendee / Wallet by BudgetBakers (CZ/SK) — https://www.spendee.com, https://budgetbakers.com | „Peňaženky“ = farebné bloky per účet → u nás **miesta** ako farebné bloky; stredoeurópsky kontext (SK účty, IBAN, VS) | priveľa gradientov a ikoniek |
| Finanzguru (DE) — https://www.finanzguru.de | Zmluvy (Verträge) ako prvotriedna entita: dodávateľ, cena, ďalšia platba, „môžeš ušetriť“ — náš budúci modul odporúčaní | tmavomodrý gradient + tyrkys = vyzerá ako fintech reklama |
| Linear — https://linear.app | Disciplína: jedna rodina písma, hustota, žiadna dekorácia, klávesnica | nástroj pre tímy; pre jedného človeka na mobile priveľmi strohé |

## Vzory kategórie (čo majú dobré produkty spoločné)
1. Domovská obrazovka odpovedá na jednu otázku: „koľko ma tento mesiac stoja domácnosti a čo ešte príde“.
2. Obdobie sa prepína na jednom mieste v hlavičke (◀ mesiac ▶), všetko pod tým sa prepočíta.
3. Peniaze a spotreba sú vedľa seba, nie na dvoch kartách; spotreba ako stĺpce po dňoch.
4. Rozpad po entite (účet / peňaženka / miesto) farbou, ktorá je stála naprieč appkou.
5. „Čaká na teba“ je viditeľné hneď (badge), ale neprekrýva hlavné číslo.
6. Faktúry ako zoznam s dátumom splatnosti a stavom zaplatená / čaká; dodávateľ ako prvé slovo.
7. Tabulkové číslice, zarovnanie súm doprava, jednotky menším písmom.

## Kde sa odlíšime
- **Svet témy je elektromer, odpočet, faktúra** — nie „fintech“. Číslice ako na počítadle, pásiky farebnej pásky ako na potrubí, stav „odhad“ vs. „podľa faktúry“ rozlíšený tvarom (prerušovaná vs. plná), nie len farbou.
- **Miesta sú hlavná os** (byt, dom v Belej, chalupa), nie kategórie — nikto z referencií nestavia na viacerých domácnostiach jednej osoby.
- **Upload je primárna akcia** (odfotiť účtenku, hodiť PDF), nie ručné zadávanie — tlačidlo je vždy na dosah palca.
