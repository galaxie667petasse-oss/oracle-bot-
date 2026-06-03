# Shadow Progress Dashboard V8.9

## Objectif

`shadow_progress_dashboard.py` combine le ledger, le lifecycle et l'evidence gate pour donner une vue claire :

- observations totales ;
- pending closing ;
- pending results ;
- completed ;
- CLV coverage ;
- ROI coverage ;
- progression sample vers 30, 100, 500 et 1000.

## Commande

```bash
python shadow_progress_dashboard.py --ledger reports/shadow_ledger.csv --lifecycle reports/event_lifecycle.json --evidence reports/evidence_gate.json --output reports/shadow_progress_dashboard.html --json reports/shadow_progress_dashboard.json
```

Ce dashboard ne valide pas une strategie. Il montre seulement si la collecte avance.
