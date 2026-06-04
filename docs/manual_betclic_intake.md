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
## V9.1 Proof Loop

La saisie Betclic manuelle reste utile pour le shadow live: taken odds au moment de l'observation, near-close plus tard, puis resultat. V9.1 ajoute `near_close_batch_runner.py` et `proof_dashboard.py` pour montrer ce qui manque avant toute conclusion.

## V9.2 Fallback manuel

API-Football peut parfois fournir des odds exploitables apres enrichment fixtures. Si `api_football_matchday_probe.py` ou `source_coverage_report.py` indique `manual_betclic_required`, le chemin manuel reste le plus propre:

1. creer le template Betclic;
2. saisir 1 a 3 observations;
3. importer en dry-run;
4. capturer la near-close plus tard;
5. renseigner le resultat;
6. relire l'evidence gate.

Le manuel ne doit pas contourner les controles: cote decimale plausible, date, marche, side, bookmaker, near-close et resultat restent obligatoires pour une CLV propre.

Ne pas melanger taken odds et near-close. Ne pas remplir une closing si elle n'a pas ete observee.
