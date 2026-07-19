# OpenAI Pricing Snapshot

Date de verification: 2026-07-19.

Sources officielles consultees:

- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [Responses API](https://platform.openai.com/docs/api-reference/responses)
- [Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Batch API](https://platform.openai.com/docs/guides/batch)

## Tarifs short-context saisis

| Modele logique | Modele configure | Input / 1M | Cached input / 1M | Output / 1M |
|---|---:|---:|---:|---:|
| FAST | `gpt-5.6-luna` | USD 1.00 | USD 0.10 | USD 6.00 |
| SPECIALIST | `gpt-5.6-terra` | USD 2.50 | USD 0.25 | USD 15.00 |
| FINAL | `gpt-5.6-sol` | USD 5.00 | USD 0.50 | USD 30.00 |

Les ecritures de cache explicites peuvent etre plus couteuses que les entrees ordinaires. Le systeme ne force donc pas de cache explicite sans mesure de benefice.

## Politique

- Les prix vivent dans `v10/llm/budgets/pricing.py` et sont versionnes.
- Si un modele n'a pas de prix connu, le budget manager echoue ferme.
- La disponibilite runtime des modeles doit etre verifiee avant tout appel autorise.
- Aucun appel OpenAI reel n'a ete effectue pendant cette phase.

