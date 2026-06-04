# V9.1 Near-Close Batch Runner

Objectif: preparer les commandes near-close par ligue a partir du shadow ledger.

Commande sans reseau:

```powershell
python near_close_batch_runner.py --ledger reports/shadow_ledger.csv --sport-map config/sport_key_map.example.json --dry-run --output reports/near_close_batch_runner.json --html reports/near_close_batch_runner.html
```

Le runner:

- lit les observations shadow sans closing;
- mappe les ligues vers les sport keys The Odds API;
- prepare les commandes;
- ne lance aucun reseau sans `--allow-network`;
- peut matcher des CSV near-close existants via `--apply-existing`, en dry-run par defaut.

Regle de securite: les near-close ne deviennent jamais des taken odds.
