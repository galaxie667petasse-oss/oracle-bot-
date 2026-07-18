# Phase 3 Statistical Log

Date locale : 2026-07-18.

## Checkpoint

- Branche : `codex/v10-hybrid-engine`.
- Commit checkpoint cree : `121ab17 feat(v10): add temporal persistence and provider replay foundation`.
- Tests avant checkpoint : compileall OK, pytest `20 passed`, secret scan `0`, boucle historique `119/119`.

## Implementation

- Migration ajoutee : `20260718_0002_v10_statistical_schema.py`.
- Package ajoute : `v10/statistics/`.
- Tests ajoutes : `test_v10_statistics.py`.
- Demo ajoutee : `python app.py demo statistical-end-to-end --json`.

## Donnees observees

- `data/MATCHES.csv` : 230557 lignes, 2000-07-28 -> 2025-06-01, 38 competitions, 230554 scores FT, 227527 cotes 1X2.
- `data/features_modern.csv` : 528066 lignes derivees V9, 2015-2025.
- xG historique fiable : non confirme.

## Demo observee

- Dataset synthetique : 90 matchs.
- Backtest demo : 45 predictions.
- Candidats demo : 0, paper-only.
- Warnings : synthetic data only, no profit claim, no LLM used.

## Validation observee

- `python test_v10_persistence.py` : OK, migration head `20260718_0002` testee sur SQLite.
- `python test_v10_statistics.py` : OK.
- `python -m compileall -q .` : OK.
- `python -m pytest -q` : `27 passed`.
- Boucle historique `test_*.py` : `120 passed`, `0 failed`.
- `python scripts/secret_scan.py --root .` : `0` fichier problematique.
- `python project_audit.py` : OK local prudent.
- PostgreSQL local : non execute, `psql` et `docker` non disponibles dans cette session ; `db doctor` vers `localhost:5432` a expire.
- PostgreSQL CI : service `postgres:16` configure dans `.github/workflows/ci.yml`, CI distante non observee depuis Codex.

## Commandes statistiques observees

- `dataset build --from 2024-01-01 --to 2024-12-31 --limit 2 --dry-run` : `rows_seen=230554`, `rows_included=2`, dry-run.
- `model train --model elo_multiclass_v1 --from 2024-01-01 --to 2024-12-31 --limit 120 --dry-run` : `match_count=120`, train `90`, validation `30`, log loss validation `1.1364481175257874`, Brier `0.6925292667695722`, calibration `VALIDATED`.
- `backtest run --from 2024-01-01 --to 2024-12-31 --limit 140 --dry-run` : `windows=3`, `prediction_count=60`, log loss `1.1270959333151178`, Brier `0.6869238751864283`.
