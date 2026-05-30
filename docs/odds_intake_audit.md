# V8.4 Odds Intake Audit

`odds_intake_audit.py` verifie la chaine :

```text
manual CSV -> snapshots -> shadow ledger -> closing -> resultats
```

Commande :

```bash
python odds_intake_audit.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --output reports/odds_intake_audit.json --html reports/odds_intake_audit.html
```

Le rapport affiche :

- snapshots taken ;
- snapshots near-close ;
- cotes valides et invalides ;
- observations shadow liees aux snapshots ;
- near-close matchables ;
- coverage closing possible ;
- coverage closing reelle ;
- gaps : taken sans near-close, ledger sans closing, ledger sans resultat.

Verdicts :

- `no_data` ;
- `snapshots_only` ;
- `shadow_started` ;
- `closing_collection_started` ;
- `usable_for_shadow` ;
- `poor_quality`.

Un bon audit ne valide pas un signal. Il indique seulement si la collecte est assez propre pour continuer.
