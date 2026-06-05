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
