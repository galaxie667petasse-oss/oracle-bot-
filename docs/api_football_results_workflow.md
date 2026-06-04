# V9.1 API-Football Results Workflow

Objectif: preparer l'import de resultats finis pour le shadow ledger, sans reseau par defaut.

Commandes offline:

```powershell
python api_football_results_adapter.py --check-config
python api_football_results_adapter.py --dry-run --date 2026-06-03
python api_football_results_adapter.py --from-fixture tests/fixtures/api_football_results_sample.json --output reports/api_football_results.csv
python shadow_result_matcher.py --ledger reports/shadow_ledger.csv --results reports/api_football_results.csv --dry-run
```

Reseau:

```powershell
python api_football_results_adapter.py --allow-network --date 2026-06-03 --output reports/api_football_results_2026_06_03.csv
```

Le reseau exige `--allow-network` et une cle d'environnement. La cle n'est jamais affichee.

Le matcher ne met pas a jour le ledger en dry-run. Pour appliquer, relancer sans `--dry-run` apres verification humaine.
