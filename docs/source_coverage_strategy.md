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
## V9.1 Evidence Acceleration

Le catalogue `external_evidence_catalog.py` complete cette strategie: il separe sources manuelles, APIs optionnelles et datasets historiques. Une source historique n'est exploitable que si `historical_odds_schema_detector.py` confirme des cotes opening/closing decimales plausibles.

The Odds API et API-Football restent optionnels et sans reseau par defaut. Toute collecte reelle doit passer par `--allow-network` et ecrire dans `reports/`.
