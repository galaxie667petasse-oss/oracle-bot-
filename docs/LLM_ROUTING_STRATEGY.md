# Strategie de routage LLM V10

## Cascade

1. Niveau 0 : aucun LLM. Le code filtre par qualite, fraicheur, EV, incertitude et eligibility.
2. Luna : tri massif low reasoning, eventuellement batchable.
3. Terra : panels specialises, seulement pour candidats serieux.
4. Sol : juge final rare, uniquement top K et budget autorise.
5. gate deterministe : derniere decision.

## Luna

Luna sert a qualifier le dossier : `DROP`, `CONTINUE`, `NEEDS_DATA` ou `ANOMALY` via sorties structurees. Elle ne peut pas accepter un signal.

## Terra

Les 12 roles ne signifient pas 12 appels.

- Panel A Quantitative Integrity : Statistical Model Auditor, Market Pricing Analyst.
- Panel B Match Context : Recent Form, Home/Away, Schedule/Fatigue, Competition Context.
- Panel C Fresh Information : Squad, Tactical, News, uniquement si preuves horodatees existent.
- Devil's Advocate : separe pour limiter l'ancrage.
- Portfolio/Correlation : conditionnel si plusieurs candidats.

## Sol

Sol est rare. Limites initiales :

- `OPENAI_MAX_FINALISTS_PER_SCAN=3`
- `OPENAI_MAX_SOL_CALLS_PER_SCAN=2`
- `OPENAI_MAX_SOL_CALLS_PER_FIXTURE=1`

Il retourne `ACCEPT_SHADOW`, `WATCH`, `REJECT`, `INSUFFICIENT_DATA` ou `ERROR`, sans chiffre deterministe nouveau.

## Pro et max

`OPENAI_ALLOW_XHIGH`, `OPENAI_ALLOW_MAX` et `OPENAI_ALLOW_PRO` restent `false`. Ces modes sont reserves a des benchmarks explicites.

