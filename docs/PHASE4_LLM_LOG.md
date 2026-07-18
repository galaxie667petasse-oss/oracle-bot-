# Journal Phase 4 LLM

Date : 2026-07-19.

## Audit initial

- Branche attendue : `codex/v10-hybrid-engine`.
- Commits de reference detectes : `121ab17` et `0ec7f72`.
- Worktree initial propre avant modifications Phase 4.
- Tests initiaux : pytest V10 vert, tests historiques verts, compileall vert, secret scan vert.
- SDK OpenAI local : non installe.
- Appel OpenAI reel : aucun.

## Implementation

- Schema Alembic `20260719_0003` pour runs LLM, usage, findings, reviews, cache, budgets et shadow decisions.
- Provider mock, replay et OpenAI Responses dormant.
- Model registry FAST/SPECIALIST/FINAL avec Luna/Terra/Sol configurables.
- ComplexityRouter et panels Terra.
- BudgetManager fail-closed.
- Cache metier par packet hash.
- Evidence registry et validation semantique.
- Contradiction engine et gate deterministe.
- Demo offline `llm-shadow-end-to-end`.

## Limites

- Disponibilite runtime des modeles OpenAI non confirmee localement.
- Tarifs LLM placeholders, a remplacer par une table validee avant tout appel reel.
- Les sorties LLM sont mock/replay uniquement dans cette phase.
- `STATISTICAL_MODEL_VALIDATED_FOR_SIGNALS=false` reste la posture correcte.

