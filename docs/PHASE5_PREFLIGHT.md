# Phase 5 Preflight

Date: 2026-07-19.

## Git

- Branche observee: `codex/v10-hybrid-engine`.
- HEAD initial: `8b95cc3 feat(v10): add cost-optimized llm shadow orchestration`.
- Commits de reference presents: `121ab17`, `0ec7f72`, `8b95cc3`.
- Worktree initial utile: propre sauf ajout local de dependances Phase 5 dans `requirements.txt`.

## Tests initiaux

- `python -m pytest -q`: 37 passed.
- `python -m compileall -q .`: OK.
- `python scripts/secret_scan.py --root .`: 0 fichier problematique.
- Migration SQLite preflight: `20260719_0003`, puis Phase 5 ajoute `20260719_0004`.

## Outils

- Python local: 3.14.3.
- Git: disponible.
- Docker: non disponible localement.
- Railway CLI: non disponible localement.
- GitHub CLI `gh`: non disponible localement.
- CI distante: non observable depuis cette session.

## Providers et donnees

- Providers inspectes: API-Football, The Odds API, replay V10, fixtures de tests.
- Gros fichiers detectes: `data/features_modern.csv`, `reports/features_with_closing_preview.csv`; non charges integralement.
- Aucune cle lue ni affichee. Seule la presence par nom est autorisee.

## Repli

- Sans `DATABASE_URL`: les commandes `--dry-run` restent executables.
- Sans cle OpenAI: mock/replay uniquement.
- Sans Telegram: preview/local uniquement.
- Sans Railway/Docker locaux: configuration et documentation preparees, aucun deploiement.

