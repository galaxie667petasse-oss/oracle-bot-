# Plans V10

## Principe

V10 est une migration additive. Le V9.x reste executable pendant que les modules V10 deviennent la future source de verite pour les calculs deterministes.

## Phase 0 - Audit

- Lire README, configuration, Docker/Railway, scripts API, Telegram, agents, scoring, dry-run et Git.
- Documenter `docs/AUDIT_V9_6.md`.
- Verifier que les secrets ne sont jamais affiches.

Statut : fait pour la premiere passe locale.

## Phase 1 - Fondation additive

- Ajouter `v10/` sans modifier `main.py`.
- Ajouter odds no-vig, EV, CLV, data quality, candidate filtering, risk paper-only, settlement, contrats agents, final judge deterministe et demo offline.
- Ajouter `app.py doctor` et `app.py demo end-to-end`.
- Ajouter `.env.example`, `.dockerignore`, secret scan et CI offline.

Statut : implemente en premiere version.

## Phase 2 - Persistence, historisation et replay

- Ajouter SQLAlchemy 2, Alembic, configuration DB typee et masquage des secrets.
- Creer schema `v10_*` : providers, competitions, seasons, teams, fixtures, status history, bookmakers, markets, raw payloads, ingestion runs, odds snapshots et market snapshots derives.
- Ajouter repositories, unit of work, health DB et locks advisory/fallback.
- Ajouter normalisation API-Football/The Odds API depuis payloads locaux.
- Ajouter replay provider, replay run, import legacy prudent et demo persistence offline.
- Tester idempotence, `as_of`, dates UTC, Decimal et contraintes.

Statut : implemente en premiere version offline ; PostgreSQL reel reste a valider dans un environnement disposant du service.

## Phase 3 - Moteur statistique football

- Auditer les donnees historiques locales sans charger les gros dumps.
- Ajouter le schema statistique: model definitions, model versions, feature snapshots, score distributions, predictions, calibration models et evaluation runs.
- Construire un dataset temporel avec features `football_features_v1`, labels et fingerprint.
- Ajouter Elo, Poisson independant, Dixon-Coles experimental, derivation des marches, calibration, ensemble et walk-forward minimal.
- Exposer `dataset`, `model`, `predict`, `backtest` et `demo statistical-end-to-end` dans `app.py`.

Statut : implemente en premiere version offline ; PostgreSQL reel reste a observer dans CI ou environnement local avec service disponible.

## Phase 4 - LLM shadow orchestration

- Ajouter provider mock, replay et OpenAI Responses dormant.
- Router deterministic-only -> Luna -> Terra panels -> Sol rare.
- Regrouper les 12 roles en panels lorsque cela reduit le cout.
- Valider toutes les preuves par `evidence_id` et `as_of`.
- Appliquer budget, cache, contradiction engine et gate deterministe.
- Garder `LLM_ENABLED=false`, `LLM_ALLOW_PAID_CALLS=false` et budgets a zero par defaut.

Statut : implemente en premiere version mock/replay, sans appel payant.

## Phases suivantes

- Phase 5 : ingestion prematch fraiche, scheduler Railway, scans shadow automatiques, surveillance des changements et comparaison statistique seul contre statistique + LLM.
- Phase 6 : ledger signal append-only et decision/veto durcis.
- Phase 7 : Telegram preview/signaux read-only anti-doublon.
- Phase 8 : settlement, CLV et evaluation relationnelle complete.
- Phase 9 : backtesting walk-forward et ablation agents.
- Phase 10 : Docker/Railway/CI production avec health checks.
## Phase 5 - Completee localement

- Migration operationnelle `20260719_0004`.
- Scheduler dispatcher borne, jobs idempotents, leases et recovery.
- Timeline prematch T-72/T-24/T-6/T-90/T-30/T-10/near-close/results.
- Provider mocks, quotas, cache provider, freshness policy.
- Material changes et non-relance LLM inutile.
- Experience `statistical_vs_llm_shadow_v1`.
- FastAPI read-only et dashboard minimal.
- Backtest compare avec baseline marche 1X2.
- Demo offline `operational-shadow-end-to-end`.

Prochaine phase proposee: deploiement staging Railway, ajout controle des cles providers, premier scan shadow reel sans LLM payant, puis smoke OpenAI Luna plafonne.
