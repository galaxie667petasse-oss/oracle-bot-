# Telegram Pipeline Smoke Test V9.6

`telegram_pipeline_smoke_test.py` verifie la configuration Telegram, genere une preview quotidienne et teste le notifier en dry-run.

Commandes:

```bash
python telegram_pipeline_smoke_test.py --date YYYY-MM-DD --dry-run
python telegram_pipeline_smoke_test.py --date YYYY-MM-DD --allow-send --plain-text-test
```

Le mode `--allow-send --plain-text-test` envoie seulement le message court `ORACLE TEST READ ONLY`. Il ne publie jamais les observations shadow et ne logge jamais le token.

Les observations doivent etre publiees avec le publisher safe:

```bash
python telegram_shadow_publisher.py --ledger reports/shadow_ledger.csv --since-date YYYY-MM-DD --only-new --max-messages 2 --dry-run
```
