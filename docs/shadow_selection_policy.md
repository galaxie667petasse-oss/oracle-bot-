# Shadow Selection Policy V8.8

## But

`odds_shadow_selector.py` limite la transformation des snapshots en observations shadow. L'objectif est d'eviter de remplir le ledger avec toutes les issues d'un match.

## Politique par defaut

- ignorer `is_near_close=true` ;
- ignorer `is_live=true` ;
- garder seulement les cotes valides ;
- permettre `--max-events` ;
- permettre `--one-side-per-event` ;
- eviter le draw sauf demande explicite ou `--include-draw`.

## Commandes

```bash
python odds_shadow_selector.py --snapshots reports/the_odds_api_jleague_today.csv --output reports/api_shadow_selection.csv --summary-json reports/api_shadow_selection_summary.json --max-events 3 --one-side-per-event --prefer-side home
python odds_to_shadow.py --selection-csv reports/api_shadow_selection.csv --ledger reports/shadow_ledger.csv --dry-run
```

## Decision

Une selection shadow reste une observation locale. Elle ne valide aucune strategie, ne cree aucune mise et ne contourne pas l'evidence gate.

## V9.0 Coverage avant selection

Avant d'ajouter des observations, lire `source_coverage_report.py` :

- si une competition active n'est pas scannee, completer le scan ;
- si API-Football a les fixtures mais pas les odds, preferer un intake manuel limite ;
- si pending closing est eleve, ne pas ajouter de nouvelles observations avant near-close.
