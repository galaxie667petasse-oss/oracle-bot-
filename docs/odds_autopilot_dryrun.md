# Odds Autopilot Dry-Run V8.9

## Objectif

`odds_autopilot_dryrun.py` repond a la question : que faut-il faire maintenant, sans action risquee ?

Il lit :

- odds lab status ;
- event lifecycle ;
- near-close schedule ;
- real observation guard ;
- evidence gate.

## Commandes

```bash
python odds_autopilot_dryrun.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv
python odds_autopilot_dryrun.py --full
```

## Regles

- aucun reseau ;
- aucune modification du ledger ;
- aucune near-close inventee ;
- aucune mise ;
- action humaine recommandee seulement.
