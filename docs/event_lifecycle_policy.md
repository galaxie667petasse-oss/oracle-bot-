# Event Lifecycle Policy V8.9

## Objectif

`event_lifecycle_manager.py` classe chaque observation shadow selon son etat de vie :

- `pre_match_waiting_close`
- `near_close_due_soon`
- `near_close_overdue`
- `closing_captured`
- `waiting_result`
- `result_overdue`
- `complete`
- `invalid`

Le module ne recupere aucune cote, ne modifie pas le ledger et n'invente jamais de kickoff.

## Commandes

```bash
python event_lifecycle_manager.py --ledger reports/shadow_ledger.csv --status
python event_lifecycle_manager.py --ledger reports/shadow_ledger.csv --due-now --minutes-before 120
python event_lifecycle_manager.py --ledger reports/shadow_ledger.csv --due-results
```

## Lecture

Un pending closing futur est normal avant match. Un `near_close_overdue` indique qu'une cote near-close reelle a probablement ete manqueee ou doit etre documentee comme absente.
