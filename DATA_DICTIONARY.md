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

## Tables Phase 3 Statistiques

- `v10_model_definitions` : definition stable d'une famille de modele (`elo_multiclass_v1`, `poisson_independent_v1`, `dixon_coles_v1`, `ensemble_v1`).
- `v10_model_versions` : version immutable d'un modele avec periode d'entrainement, hyperparametres, fingerprint dataset, metriques et statut DRAFT/VALIDATED/ACTIVE/RETIRED/FAILED.
- `v10_feature_snapshots` : features `football_features_v1` pour une fixture et un `as_of`, avec `data_cutoff`, completude, warnings et hash source.
- `v10_score_distributions` : matrice compacte de scores, esperances de buts et masse de queue.
- `v10_statistical_predictions` : probabilites par marche/selection, probabilite brute, probabilite calibree, bornes et diagnostics.
- `v10_calibration_models` : calibrateurs Platt, isotonic ou temperature scaling avec fenetre d'entrainement et metriques avant/apres.
- `v10_evaluation_runs` : datasets, entrainements, backtests et demos persistables avec configuration, fingerprint, metriques et notes.

## Features Phase 3

Schema : `football_features_v1`.

Champs principaux : matchs joues, points par match, buts pour/contre, goal difference, forme 5/10, splits domicile/exterieur, jours de repos, matchs sur 7/14/30 jours, Elo pre-match, H2H limite, mois, indicators de missingness et `data_completeness`.

Regle temporelle : aucune feature ne peut utiliser le resultat du match cible, une cote observee apres `as_of`, ou un resultat futur. Une prediction doit etre reproductible avec son `model_version`, son `feature_snapshot` et son `prediction_fingerprint`.

## Tables Phase 4 LLM Shadow

- `v10_llm_providers` : providers LLM logiques.
- `v10_llm_model_configs` : modeles FAST/SPECIALIST/FINAL et reasoning associe.
- `v10_prompt_templates` / `v10_prompt_versions` : prompts versionnes.
- `v10_llm_runs` : appels ou replays, modele demande/utilise, packet hash, output hash, latence et statut.
- `v10_llm_tool_calls` : appels d'outils read-only bornes.
- `v10_llm_usage_records` : tokens, cout estime, cache et retries.
- `v10_agent_findings` : findings structures avec `evidence_ids`.
- `v10_contradiction_reports` : contradictions et hard vetoes detectes par code.
- `v10_final_judge_reviews` : revue Sol sans probabilite, cote, EV ou stake.
- `v10_shadow_decisions` : decision finale shadow apres gate deterministe.
- `v10_budget_reservations` : reservations et reconciliations budget.
- `v10_llm_cache_entries` : cache metier par packet hash.
- `v10_model_pricing_versions` : tarifs versionnes et modifiables.
## V10 Operational Tables

- `v10_scheduled_jobs`: file due jobs avec `job_type`, `due_at`, `status`, `idempotency_key`, `lease_owner`, `lease_expires_at`.
- `v10_job_attempts`: historique de chaque tentative, duree, statut, erreur et metriques.
- `v10_scheduler_runs`: tick dispatcher borne, heartbeat et raison de sortie.
- `v10_scan_runs`: funnel de scan prematch shadow.
- `v10_scan_targets`: prochaine action par fixture.
- `v10_provider_quota_usage`: headers de quota reellement observes, sans secret.
- `v10_provider_health`: latence, statut degrade et circuit provider.
- `v10_provider_cache_entries`: cache provider separe du cache LLM.
- `v10_material_change_events`: detection de changements materiels et decision de rescan/LLM rerun.
- `v10_shadow_experiments`: preregistration de l'experience shadow.
- `v10_shadow_experiment_decisions`: decisions append-only des bras `deterministic_only` et `deterministic_plus_llm`.
- `v10_shadow_experiment_outcomes`: outcome revele apres match seulement.
- `v10_operational_alerts`: alertes en base, aucun envoi.
- `v10_service_heartbeats`: heartbeat web/scheduler/settlement.

Toutes les dates sont timezone-aware UTC via `UTCDateTime`.
