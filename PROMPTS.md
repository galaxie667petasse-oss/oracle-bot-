# Prompts V10

Les prompts seront versionnes hors code metier dans une future arborescence `prompts/`.

## Regles de prompt

- Interdire explicitement l'invention de donnees.
- Lister les sources autorisees et leurs timestamps.
- Forcer un JSON strict.
- Rappeler que la confiance n'est pas une probabilite de gain.
- Rappeler que le LLM ne calcule pas EV, ROI, CLV ou staking.
- Exiger `INSUFFICIENT_DATA` quand les donnees manquent.
- Enregistrer prompt name, version, model, schema version, input hash et response hash.

## Etat actuel

`v10.agents` valide le schema attendu et fournit des agents mock pour replay/demo offline. Aucun appel OpenAI reel n'est effectue par V10 foundation.

