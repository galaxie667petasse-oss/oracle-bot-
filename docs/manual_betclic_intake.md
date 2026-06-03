# V9.0 Manual Betclic Intake

Quand un match est visible sur Betclic mais absent ou incomplet dans les APIs, l'utilisateur peut saisir 1 a 3 observations manuelles.

Le helper produit le meme format que les snapshots manuels:

```powershell
python manual_betclic_intake_helper.py --template reports/betclic_manual_intake.csv --date YYYY-MM-DD
python manual_betclic_intake_helper.py --validate reports/betclic_manual_intake.csv
python manual_betclic_intake_helper.py --to-matchday-pack reports/betclic_manual_intake.csv --pack reports/matchday_YYYY_MM_DD
python manual_betclic_intake_helper.py --to-shadow reports/betclic_manual_intake.csv --ledger reports/shadow_ledger.csv --dry-run
```

Regles:

- source `manual` ou `betclic_manual`;
- bookmaker Betclic par defaut;
- odds decimales strictement plausibles;
- near-close explicite avec `is_near_close=true`;
- ledger modifie seulement avec `--apply`.

Observation seulement, aucune mise.
