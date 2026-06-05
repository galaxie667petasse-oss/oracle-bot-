# V9.5 Telegram Read-Only Publisher

Cette phase ajoute une couche Telegram locale pour lire les observations shadow sans activer de signal.

Principes:

- dry-run par defaut ;
- preview Markdown avant emission ;
- emission reelle seulement avec `--allow-send` ;
- token et chat id lus depuis l'environnement local ;
- token jamais affiche ;
- `lab_only=true` et `can_influence_picks=false` ;
- aucune mise, aucun staking, aucun Kelly, aucune promesse.

Commandes principales:

```bash
python telegram_config.py --check
python telegram_daily_reporter.py --date YYYY-MM-DD --dry-run
python telegram_shadow_publisher.py --ledger reports/shadow_ledger.csv --dry-run
python telegram_result_reporter.py --ledger reports/shadow_ledger.csv --dry-run
python telegram_ops_runner.py --date YYYY-MM-DD --full-dry-run
```

Emission reelle, uniquement apres verification des previews:

```bash
python telegram_ops_runner.py --date YYYY-MM-DD --morning --allow-send
python telegram_ops_runner.py --date YYYY-MM-DD --pre-close --allow-send
python telegram_ops_runner.py --date YYYY-MM-DD --post-match --allow-send
```

Telegram read-only ne change pas la gouvernance. L'evidence gate reste l'autorite: sample faible, CLV absente ou preuve incomplete impliquent `non valide`.
