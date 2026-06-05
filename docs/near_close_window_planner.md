# V9.4 - Near-Close Window Planner

`near_close_window_planner.py` lit `reports/shadow_ledger.csv` et indique quelles observations ont besoin d'une capture near-close.

Statuts:

- `too_early`;
- `due_now`;
- `overdue`;
- `captured`;
- `result_due`.

Le module n'appelle aucune API. Il propose seulement une commande possible: API-Football si un `source_event_id` est disponible, near-close batch si la ligue a un mapping sport key, ou fallback manuel.

Commande:

```bash
python near_close_window_planner.py --ledger reports/shadow_ledger.csv --hours-before 2
```
