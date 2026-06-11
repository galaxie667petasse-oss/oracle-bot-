# V9.5 Telegram Read-Only Publisher

Cette phase ajoute une couche Telegram locale pour lire les observations shadow sans activer de signal.

Principes:

- dry-run par defaut ;
- preview Markdown ou plain text avant emission ;
- emission reelle seulement avec `--allow-send` ;
- token et chat id lus depuis l'environnement local ;
- token jamais affiche ;
- `lab_only=true` et `can_influence_picks=false` ;
- aucune mise, aucun staking, aucun Kelly, aucune promesse.

Commandes principales:

```bash
python telegram_config.py --check
python telegram_notifier.py --message-file reports/telegram_test_message.md --dry-run
python telegram_daily_reporter.py --date YYYY-MM-DD --dry-run
python telegram_shadow_publisher.py --ledger reports/shadow_ledger.csv --dry-run
python telegram_result_reporter.py --ledger reports/shadow_ledger.csv --dry-run
python telegram_ops_runner.py --date YYYY-MM-DD --full-dry-run
```

Emission reelle, uniquement apres verification des previews:

```bash
python telegram_notifier.py --message-file reports/telegram_test_message.md --allow-send --plain-text
python telegram_notifier.py --message-file reports/telegram_daily_preview.md --allow-send --show-error-detail
python telegram_ops_runner.py --date YYYY-MM-DD --morning --allow-send
python telegram_ops_runner.py --date YYYY-MM-DD --pre-close --allow-send
python telegram_ops_runner.py --date YYYY-MM-DD --post-match --allow-send
```

Diagnostic V9.5.1:

- `telegram_notifier.py` lit les fichiers en `utf-8-sig` et retire seulement les BOM invisibles de debut de fichier ;
- `TELEGRAM_PARSE_MODE` vide supprime `parse_mode` du payload ;
- si Markdown echoue avec `can't parse entities`, le notifier retente automatiquement le meme chunk sans `parse_mode` ;
- les logs d'erreur conservent `error_code`, `description`, `retry_after`, `chunk_index`, `parse_mode` et `fallback_used` ;
- le token et l'URL complete contenant le token ne doivent jamais etre imprimes ni logges.

Telegram read-only ne change pas la gouvernance. L'evidence gate reste l'autorite: sample faible, CLV absente ou preuve incomplete impliquent `non valide`.

## Publication safe V9.6

Pour eviter de republier les anciennes observations:

```bash
python telegram_shadow_publisher.py --ledger reports/shadow_ledger.csv --mark-existing-as-published --dry-run
python telegram_shadow_publisher.py --ledger reports/shadow_ledger.csv --since-date YYYY-MM-DD --only-new --max-messages 2 --dry-run
python telegram_shadow_publisher.py --ledger reports/shadow_ledger.csv --since-date YYYY-MM-DD --only-new --max-messages 2 --allow-send
```

Si `--only-new` est utilise sans tracking existant et sans `--since-date`, le publisher ignore les anciennes observations pour eviter le spam. Une selection vide n'envoie aucun message Telegram.

Smoke test pipeline:

```bash
python telegram_pipeline_smoke_test.py --date YYYY-MM-DD --dry-run
python telegram_pipeline_smoke_test.py --date YYYY-MM-DD --allow-send --plain-text-test
```
