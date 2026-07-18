# V9.8 Shadow Result Settlement

Objectif: appliquer un resultat final au shadow ledger local, sans reseau, sans mise et sans pick automatique.

## Commandes

Dry-run Ghana - Panama:

```bash
python shadow_result_matcher.py --ledger reports/shadow_ledger.csv --results reports/api_football_results_2026-06-17.csv --target-shadow-id sh_20260617210447_2ee081d9 --dry-run
```

Application ledger apres verification humaine:

```bash
python shadow_result_matcher.py --ledger reports/shadow_ledger.csv --results reports/api_football_results_2026-06-17.csv --target-shadow-id sh_20260617210447_2ee081d9 --apply
```

Regeneration preuve:

```bash
python shadow_clv_report.py --ledger reports/shadow_ledger.csv --output reports/shadow_clv_report.json --html reports/shadow_clv_report.html
python evidence_gate.py --clv-report reports/shadow_clv_report.json --quality-report reports/shadow_quality_audit.json
python proof_dashboard.py --shadow reports/shadow_clv_report.json --evidence reports/evidence_gate.json --quality reports/shadow_quality_audit.json --output reports/proof_dashboard.json --html reports/proof_dashboard.html
```

## Matching

Ordre de matching:

1. `fixture_id` / `source_event_id` exact si disponible.
2. Date + ligue + home normalise + away normalise.
3. Aucun matching approximatif sans date.

Si plusieurs resultats sont possibles, le statut est ambigu et aucune application de resultat n'est faite. Si le match n'est pas termine, le matcher signale `skipped_not_finished`.

## Colonnes V9.8

Le matcher ajoute si besoin:

- `result_status`
- `result_home_goals`
- `result_away_goals`
- `result_winner`
- `result_date`
- `result_source`
- `result_fixture_id`
- `result_captured_at`
- `is_result_final`
- `profit_units`
- `roi_percent`
- `settled_at`
- `settlement_status`

Le champ legacy `result` reste synchronise pour compatibilite.

## Ghana - Panama

Resultat attendu:

- fixture: `1489385`
- score: Ghana `1` - `0` Panama
- observation: `h2h home`
- cote prise: `2.26`
- result_status: `win`
- profit_units: `1.26`
- roi_percent: `126.0`
- settlement_status: `settled`

Ce completed cycle reste une observation laboratoire. Il ne valide aucun edge et ne peut pas influencer les picks.

## Garde-fous

- Dry-run par defaut.
- Ecriture ledger seulement avec `--apply`.
- `--overwrite` requis pour remplacer un resultat existant.
- Aucun reseau dans les tests.
- Aucun fichier `data/` modifie.
- `reports/` et `external_data/` restent non trackes.
- `lab_only=true`.
- `can_influence_picks=false`.
