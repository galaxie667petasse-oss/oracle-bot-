# Security V10

## Secrets

Ne jamais afficher, logger ou committer les valeurs de `API_FOOTBALL_KEY`, `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `DATABASE_URL`, tokens Railway ou GitHub.

## Fichiers ignores

`data/`, `reports/`, `external_data/`, `variable/`, `.env` et `oracle_db*.json` restent hors Git et hors Docker context.

## Telegram

Telegram est desactive par defaut. L'envoi reel exige `--allow-send`, une configuration valide et `TELEGRAM_DISABLE_SEND=false`.

## Argent reel

`REAL_MONEY_ACTIONS_ENABLED=false`. La couche V10 ne supporte aucune action bookmaker et ne place aucune mise.

## CI

Le workflow CI lance un secret scan, compile le projet, execute les tests V10 et construit Docker. Aucun appel fournisseur ou Telegram reel n'est autorise.

## LLM Phase 4

Defaults securises :

- `LLM_ENABLED=false`
- `LLM_SHADOW_ONLY=true`
- `LLM_ALLOW_PAID_CALLS=false`
- `OPENAI_DAILY_BUDGET_USD=0`
- `OPENAI_SCAN_BUDGET_USD=0`
- `OPENAI_FIXTURE_BUDGET_USD=0`
- `OPENAI_ALLOW_XHIGH=false`
- `OPENAI_ALLOW_MAX=false`
- `OPENAI_ALLOW_PRO=false`

Le provider OpenAI est isole derriere une interface et refuse l'appel si les flags ne sont pas simultanement ouverts. Les outils LLM sont read-only et ne peuvent pas acceder au shell, a Telegram, aux secrets, a un bookmaker ou a SQL libre.
