# Configuration Telegram Locale

Creer un bot avec BotFather, puis renseigner les variables localement sans les committer:

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_DISABLE_SEND=true
TELEGRAM_PARSE_MODE=Markdown
```

Un modele vide est fourni dans `config/telegram.example.env`.

Verification:

```bash
python telegram_config.py --check
python telegram_config.py --show-safe
```

`TELEGRAM_DISABLE_SEND=true` bloque l'emission meme si le token existe. Pour envoyer une preview verifiee, il faut:

1. configurer les variables localement ;
2. mettre `TELEGRAM_DISABLE_SEND=false` ;
3. lancer une commande avec `--allow-send`.

Aucun token ne doit apparaitre dans Git, dans les logs ou dans les rapports.

## Parse mode et diagnostic 400

Pour tester un envoi sans Markdown Telegram:

```powershell
$env:TELEGRAM_PARSE_MODE=""
python telegram_notifier.py --message-file reports/telegram_test_message.md --allow-send --plain-text
```

Pour garder Markdown mais afficher le detail Telegram en cas d'erreur:

```powershell
python telegram_notifier.py --message-file reports/telegram_daily_preview.md --allow-send --show-error-detail
```

En cas de `400 Bad Request` lie a Markdown, le notifier logge la reponse Telegram sans token et retente automatiquement en plain text si la description contient `can't parse entities`.
