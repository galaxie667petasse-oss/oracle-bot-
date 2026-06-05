# V9.4 - Post-Match Results Runner

`post_match_results_runner.py` repere les dates du ledger dont les resultats sont encore inconnus, recupere ou lit des resultats API-Football normalises, puis appelle `shadow_result_matcher.py`.

Regles:

- aucun reseau sans `--allow-network`;
- aucun resultat invente;
- aucune mise a jour du ledger sans `--apply`;
- matching prudent par fixture id ou date/ligue/equipes.

Commande:

```bash
python post_match_results_runner.py --ledger reports/shadow_ledger.csv --allow-network --dates-from-ledger --dry-run
```
