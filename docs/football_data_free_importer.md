# V9.4 - Football-Data Free Importer

`football_data_free_importer.py` importe un CSV Football-Data gratuit vers un CSV normalise dans `reports/`, sans modifier `data/`.

Le module detecte:

- resultats `FTHG/FTAG/FTR`;
- odds H2H classiques comme `B365H/B365D/B365A`;
- colonnes closing explicites si elles existent et ressemblent a des cotes decimales.

Si seules des cotes opening, max ou moyennes existent, le rapport indique `historical_odds_available_but_closing_uncertain`. Aucune CLV n'est calculee sans vraie closing plausible.

Commande:

```bash
python football_data_free_importer.py --csv external_data/football_data/E0.csv --output reports/football_data_normalized.csv --summary-json reports/football_data_import_summary.json --html reports/football_data_import_summary.html
```
