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

## Phases suivantes

- Phase 4 : Elo, Poisson, Dixon-Coles si donnees suffisantes, calibration et incertitude.
- Phase 5 : candidate engine historique, correlation et budget LLM.
- Phase 6 : agents LLM stricts avec mocks, schemas et prompts versionnes.
- Phase 7 : juge final, veto, ledger signal append-only.
- Phase 8 : Telegram preview/signaux read-only anti-doublon.
- Phase 9 : settlement, CLV et evaluation.
- Phase 10 : backtesting walk-forward et ablation agents.
- Phase 11 : Docker/Railway/CI production avec health checks.
