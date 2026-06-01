# Matchday Phase Workflow

V8.7 rend le workflow matchday explicite par phase.

## Phases

- `pre_match` : les taken odds sont attendues. Les near-close et les resultats sont encore absents normalement.
- `near_close` : les taken odds et near-close sont attendues. Les resultats restent absents normalement.
- `post_match` : taken odds, near-close et resultats sont attendus.
- `full_day` : etat mixte accepte avec warnings clairs.

## Commandes

```bash
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run --phase pre_match
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run --phase near_close
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run --phase post_match
```

En `pre_match`, l'absence de near-close n'est pas un blocage. Elle devient un blocage en `near_close` et `post_match`.

Le statut reste laboratoire local : observation shadow, aucune mise, aucune activation Telegram ou Railway.
