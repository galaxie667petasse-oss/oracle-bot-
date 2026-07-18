# LLM Shadow Mode V10

Le mode shadow est obligatoire en Phase 4.

`SHADOW_ACCEPTED` signifie seulement :

- le dossier passe les filtres deterministes ;
- les preuves LLM mock/replay sont valides ;
- le juge ne voit pas de veto non resolu ;
- le gate deterministe accepte une observation shadow.

Cela ne signifie pas :

- pari reel ;
- Telegram reel ;
- rentabilite attendue ;
- modeles valides pour signaux ;
- staking ou Kelly.

Demo offline :

```bash
python app.py demo llm-shadow-end-to-end --mock --json
```

Scenarios :

1. rejet deterministe avant LLM ;
2. rejet par hard veto ;
3. donnees insuffisantes ;
4. shadow accepted.

La demo affiche routing, appels, cache, budget fictif, contradictions, decision finale et `telegram_sent=false`.

