# V9.1 Historical CLV Import Workflow

Objectif: accelerer la preuve avec un CSV historique externe qui contient de vraies cotes opening et closing decimales.

Regles:

- ne jamais utiliser une colonne detectee par nom si les valeurs ne ressemblent pas a des cotes decimales;
- ne jamais convertir une probabilite 0-1 en cote;
- ne jamais modifier `data/MATCHES.csv` ni `data/features_modern.csv`;
- ecrire les imports normalises dans `reports/`;
- lire la preuve historique comme un contexte, pas comme une validation live.

Workflow:

```powershell
python historical_odds_schema_detector.py --csv reports/historical_odds_candidate.csv --output reports/historical_odds_schema.json --html reports/historical_odds_schema.html
python historical_clv_importer.py --csv reports/historical_odds_candidate.csv --schema reports/historical_odds_schema.json --output reports/historical_clv_import.csv --summary-json reports/historical_clv_import_summary.json
python historical_clv_backtester.py --input reports/historical_clv_import.csv --output reports/historical_clv_backtest.json --html reports/historical_clv_backtest.html
```

Si le schema detector retourne `no_usable_closing`, l'import CLV doit etre abandonne.

Statut final: preuve historique seulement. Le shadow live reste obligatoire avant toute analyse approfondie.
