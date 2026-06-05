# V9.4 - Daily Operations Runner

`daily_operations_runner.py` regroupe la routine de juin:

- `morning`: next-days dry-run et source coverage;
- `pre-close`: plan near-close et near-close batch dry-run;
- `post-match`: resultats, shadow CLV report, evidence gate;
- `full-dry-run`: tout sans reseau.

Il ne lance aucun reseau sans `--allow-network`, et ne fait aucun apply implicite.

Commande:

```bash
python daily_operations_runner.py --date YYYY-MM-DD --full-dry-run
```
