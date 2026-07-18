# Data Dictionary V10

## Concepts principaux

- `fixture_id` : identifiant interne ou provider de l'evenement.
- `event_time` : heure reelle de l'evenement sportif.
- `observed_at` : heure a laquelle Oracle observe une donnee.
- `effective_at` : heure a partir de laquelle une information est valide pour decision.
- `created_at` / `updated_at` : timestamps techniques UTC.

## Marches initiaux

- `match_winner` : home, draw, away.
- `draw_no_bet` : home, away, push si nul.
- `double_chance` : 1x, 12, x2.
- `total_goals` : over/under avec `line`.
- `both_teams_to_score` : yes/no.

## Sorties V10

- `quality_report.status` : PASS, PASS_WITH_WARNINGS, FAIL, STALE, CONFLICTING.
- `candidate.decision` : candidate ou rejected.
- `final_judge.decision` : BET, WATCH, NO_BET, INSUFFICIENT_DATA. La demo retourne WATCH sans validation LLM reelle.
- `settlement.result_status` : win, loss, push, void, unknown.
- `profit_units` : profit shadow par unite fictive, jamais mise reelle.

## Tables cibles

Les futures phases devront encore couvrir `feature_snapshots`, `statistical_predictions`, `agent_runs`, `decision_runs`, `betting_signals`, `signal_publications`, `fixture_results`, `settlements`, `clv_records`, `evaluation_runs`, `job_runs` et `llm_usage_records`.

## Tables Phase 2

- `v10_providers` : providers normalises, cle unique.
- `v10_competitions` : competition par provider et external ID.
- `v10_seasons` : saison rattachee a une competition.
- `v10_teams` : equipes par provider et external ID.
- `v10_fixtures` : match canonique, `event_time`, statuts et dernier `observed_at`.
- `v10_fixture_status_history` : historique append-only des statuts observes.
- `v10_bookmakers` : bookmakers par provider.
- `v10_markets` : marches canoniques supportes.
- `v10_market_selections` : selections par marche et ligne.
- `v10_ingestion_runs` : execution d'ingestion/replay.
- `v10_raw_api_payloads` : payload brut JSONB, hash et contexte nettoye.
- `v10_odds_snapshots` : snapshot immuable de cote observee.
- `v10_normalized_market_snapshots` : table derivee reservee aux consensus no-vig futurs.
- `v10_advisory_locks` : fallback SQLite pour locks de replay.

## Politique JSONB

JSONB est reserve aux payloads bruts, metadata provider, parametres rares et champs derives non encore modelises. Les entites interrogees frequemment restent relationnelles : fixtures, teams, competitions, bookmakers, markets et odds.
