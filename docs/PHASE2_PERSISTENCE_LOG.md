# Phase 2 Persistence Log

Date locale : 2026-07-18.

## Audit initial

- Branche : `codex/v10-hybrid-engine`.
- HEAD detecte : `4d42466 Apply API-Football near-close odds to shadow ledger`.
- Commit de fondation V10 detecte : non. Les changements V9.8 et V10 foundation sont encore non commites dans le worktree.
- Modifications V9.8 preexistantes non commitees : `shadow_result_matcher.py`, `shadow_ledger.py`, `shadow_clv_report.py`, `proof_dashboard.py`, `evidence_gate.py`, `telegram_result_reporter.py`, `oracle_ops.py`, `report_runner.py` et tests/docs associes.
- Fondation V10 preexistante non commitee : `v10/`, `app.py`, `.env.example`, `.dockerignore`, `.github/workflows/ci.yml`, docs V10 et `test_v10_foundation.py`.

## Payloads inspectes prudemment

- `tests/fixtures/api_football_fixtures_sample.json` : 946 octets.
- `tests/fixtures/api_football_odds_sample.json` : 866 octets.
- `tests/fixtures/api_football_results_sample.json` : 528 octets.
- `tests/fixtures/the_odds_api_sample.json` : 770 octets.
- Les artefacts `reports/` ont ete listes par taille avant lecture; aucun gros fichier n'a ete charge.

## Baseline tests avant modifications Phase 2

- Commande : boucle PowerShell sur `test_*.py`.
- Resultat observe : `TOTAL=118 PASSED=118 FAILED=0`.

## Validations apres implementation Phase 2

- `python test_v10_persistence.py` : OK.
- `python test_v10_foundation.py` : OK.
- `python -m compileall -q .` : OK.
- `python -m pytest -q` : `20 passed`.
- Boucle PowerShell sur `test_*.py` : `TOTAL=119 PASSED=119 FAILED=0`.
- `python scripts/secret_scan.py --root .` : `Fichiers problematiques: 0`.
- `python project_audit.py` : statut release candidate OK local prudent.

## Demo persistence observee

- Commande : `python app.py demo postgres-end-to-end --json`.
- Dialecte utilise localement : SQLite temporaire.
- PostgreSQL teste localement : non, `psql` et Docker ne sont pas disponibles dans cet environnement.
- Migration observee : revision `20260718_0001`, `up_to_date=true`.
- Fixtures normalisees : 1.
- Odds snapshots apres replay initial, doublon et cote modifiee : 13.
- Rejeu identique : `inserted=0`, `ignored=25`.
- `as_of` avant modification home odds : `2.1000`.
- `as_of` apres modification home odds : `2.2400`.
- Qualite fixture reconstruite : `PASS`.

## Legacy discover observe

- Commande : `python app.py legacy discover --max-bytes 1000`.
- Total detecte : 886 fichiers.
- Trop volumineux et non charges : 507 fichiers.
- Les gros dumps `reports/` et `external_data/` ont ete marques `too_large`.
