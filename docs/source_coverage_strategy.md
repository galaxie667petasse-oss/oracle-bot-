# V9.0 Source Coverage Strategy

Le coverage source compare:

- sports soccer actifs The Odds API;
- scanner The Odds API;
- fixtures API-Football;
- odds API-Football si disponibles;
- packs manuels Betclic.

Le but est de savoir quelle source utiliser pour suivre un match aujourd'hui ou demain. Le rapport ne cree aucun signal et ne lance aucune collecte reseau.

Recommandations possibles:

- API automatique si le sport key est actif et proche;
- manuel Betclic si fixtures visibles mais odds API absentes;
- attendre near-close;
- ignorer si la competition est hors scope ou trop lointaine.

Commande:

```powershell
python source_coverage_report.py --the-odds-scan reports/soccer_odds_sport_scan.json --output reports/source_coverage_report.json --html reports/source_coverage_report.html
```

Evidence gate reste decisionnel.
