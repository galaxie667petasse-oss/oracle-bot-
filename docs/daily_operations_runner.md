# V9.4 - Daily Operations Runner

`daily_operations_runner.py` regroupe la routine de juin:

- `morning`: next-days dry-run et source coverage;
- `pre-close`: plan near-close et near-close batch dry-run;
- `post-match`: resultats, shadow CLV report, evidence gate;
- `full-dry-run`: tout en dry-run ledger, reseau seulement si `--allow-network` est explicitement present.

Il ne lance aucun reseau sans `--allow-network`, et ne fait aucun apply implicite.

Commande:

```bash
python daily_operations_runner.py --date YYYY-MM-DD --full-dry-run
python daily_operations_runner.py --date YYYY-MM-DD --allow-network --morning
```

Depuis V9.6, `--allow-network` est propage au next-days runner meme quand le ledger reste en dry-run. La console affiche:

- `Reseau autorise: True/False`
- `Morning scan: network True/False`
- `Next-days runner: network True/False`

Pour diagnostiquer le scan sans ledger:

```bash
python live_scan_smoke_test.py --date YYYY-MM-DD --days 2 --allow-network --debug
```
## Publication Telegram read-only

Le runner quotidien V9.4 alimente V9.5 via `telegram_daily_reporter.py`.

```bash
python telegram_daily_reporter.py --date YYYY-MM-DD --dry-run
python telegram_ops_runner.py --date YYYY-MM-DD --full-dry-run
```

Le mode Telegram ne lance pas de reseau de donnees sportives et n'envoie rien sans `--allow-send`.
