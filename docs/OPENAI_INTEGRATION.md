# Integration OpenAI V10

Phase 4 ajoute un provider OpenAI dormant sous `v10.llm.providers.openai_responses`.

## Etat

- Aucun appel OpenAI reel n'est lance par defaut.
- Le SDK `openai` n'etait pas installe localement pendant l'implementation.
- Les noms `gpt-5.6-luna`, `gpt-5.6-terra` et `gpt-5.6-sol` sont des valeurs configurables du projet. Leur disponibilite runtime doit etre verifiee avec une cle API et les flags explicites.
- La documentation officielle consultee pour l'orientation API est :
  - https://platform.openai.com/docs/api-reference/responses
  - https://platform.openai.com/docs/guides/structured-outputs
  - https://platform.openai.com/docs/models

## Garde-fous

Un appel payant exige simultanement :

- `LLM_ENABLED=true`
- `LLM_ALLOW_PAID_CALLS=true`
- budget positif
- option CLI `--allow-paid`

La presence de `OPENAI_API_KEY` ne suffit jamais.

## Responses API

Le provider isole l'appel `responses.create` derriere une interface `LLMProvider`. Le code metier n'importe jamais directement le client OpenAI.

Le smoke reel existe mais reste bloque tant que les flags et budgets ne sont pas explicitement ouverts :

```bash
python app.py llm smoke --tier fast --allow-paid --max-cost-usd 0.05
```

