# Result Capture Workflow V8.9

## Objectif

`result_capture_helper.py` prepare un CSV de resultats manuels pour les observations shadow, puis valide ou applique ces resultats via le ledger.

## Commandes

```bash
python result_capture_helper.py --ledger reports/shadow_ledger.csv --template reports/manual_results_due.csv
python result_capture_helper.py --ledger reports/shadow_ledger.csv --results reports/manual_results_due.csv --dry-run
python result_capture_helper.py --ledger reports/shadow_ledger.csv --results reports/manual_results_due.csv --apply
```

## Resultats valides

- `win`
- `loss`
- `push`
- `void`
- `unknown`

Le dry-run doit toujours preceder l'apply. Aucun resultat n'est invente.
