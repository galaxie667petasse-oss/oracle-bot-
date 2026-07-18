# Securite LLM V10

Defaults :

```env
LLM_ENABLED=false
LLM_SHADOW_ONLY=true
LLM_ALLOW_PAID_CALLS=false
OPENAI_DAILY_BUDGET_USD=0
TELEGRAM_ENABLED=false
TELEGRAM_DISABLE_SEND=true
REAL_MONEY_ACTIONS_ENABLED=false
```

## Interdits

- pas de SQL libre ;
- pas de shell ;
- pas de navigateur libre ;
- pas d'ecriture fichier ;
- pas de Telegram ;
- pas de bookmaker ;
- pas de secret dans les prompts ;
- pas de resultat futur dans un packet.

## Outils read-only

Les outils LLM sont des facades bornees : candidate snapshot, fixture snapshot, model predictions, market snapshot, odds history, quality report, evidence item, findings valides. Ils appliquent `as_of`, verifient la fixture et limitent la taille.

Le gate deterministe reste souverain meme si Sol accepte.

