# Dry-Run Staging

V8.7 corrige le dry-run matchday.

Avant V8.7, `matchday_runner.py --full-dry-run` validait les taken odds mais ne les ecrivait pas dans un store temporaire. Les etapes suivantes lisaient donc le store reel, souvent vide, ce qui rendait le dry-run trompeur.

Depuis V8.7, le full-dry-run cree un staging temporaire :

1. store odds snapshots temporaire ;
2. shadow ledger temporaire ;
3. import taken odds dans le store temporaire ;
4. conversion taken vers observation shadow temporaire ;
5. import near-close temporaire si disponible ;
6. matching closing temporaire ;
7. import resultats temporaire si disponible.

Le dry-run ne modifie pas les vrais fichiers `reports/odds_snapshots.csv` ou `reports/shadow_ledger.csv`.

Champs utiles dans la sortie :

- `staged_store_rows` ;
- `staged_ledger_rows` ;
- `staged_taken_imported` ;
- `staged_shadow_created` ;
- `staged_near_close_imported` ;
- `staged_closing_matched` ;
- `staged_results_imported` ;
- `stage_warnings` ;
- `next_actions`.

Si une ligne taken valide est presente en `pre_match`, le dry-run doit montrer qu'une observation shadow pourrait etre creee, meme si le store reel est vide.
