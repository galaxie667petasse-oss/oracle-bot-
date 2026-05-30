# June Shadow Runbook

## Routine quotidienne matin

1. Lancer `python oracle_ops.py --health`.
2. Lancer `python oracle_ops.py --daily`.
3. Verifier les observations shadow du jour.
4. Generer les templates si besoin.
5. Ne rien conclure avant CLV et resultats.

## Avant match

1. Noter le match, la ligue, le marche et le side.
2. Noter la cote prise observee.
3. Noter le bookmaker/source.
4. Ecrire la raison en langage descriptif.
5. Garder le statut `observation` ou `watchlist`.

Commande possible :

```bash
python shadow_ledger.py --add --match-date 2026-06-01 --league EPL --home "Arsenal" --away "Chelsea" --market h2h --side home --taken-odds 2.10 --bookmaker manual --strategy-name test_signal --reason "observation shadow"
```

## Apres match

1. Remplir la closing odds manuelle si elle vient d'une source fiable.
2. Importer la closing :

```bash
python closing_manual_import.py --ledger reports/shadow_ledger.csv --closing-csv reports/manual_closing_import.csv
```

3. Remplir le resultat.
4. Importer le resultat :

```bash
python results_manual_import.py --ledger reports/shadow_ledger.csv --results-csv reports/manual_results_import.csv
```

## Rapport quotidien

```bash
python shadow_quality_audit.py --ledger reports/shadow_ledger.csv --output reports/shadow_quality_audit.json --html reports/shadow_quality_audit.html
python shadow_clv_report.py --ledger reports/shadow_ledger.csv --output reports/shadow_clv_report.json --html reports/shadow_clv_report.html
python evidence_gate.py --shadow-report reports/shadow_clv_report.json --quality-audit reports/shadow_quality_audit.json --big5-summary reports/big5_xg_summary.json --clv-readiness reports/clv_readiness.json --output reports/evidence_gate.json --html reports/evidence_gate.html
python sample_size_planner.py --shadow-report reports/shadow_clv_report.json --output reports/sample_size_plan.json --html reports/sample_size_plan.html
```

## Quand ignorer une observation

- cote absente ou non decimale ;
- closing odds non fiable ;
- match mal identifie ;
- marche ou side ambigu ;
- information post-match utilisee ;
- raison trop vague ;
- doublon probable.

## Regles de prudence

- aucune mise ;
- pas de Telegram public ;
- pas de conclusion avant sample significatif ;
- CLV obligatoire ;
- sample > 1000 minimum ;
- ROI seul ne suffit pas ;
- pas de Kelly reel ;
- pas de promesse de rentabilite.

## Exemple de journee complete

1. Matin : `oracle_ops.py --daily`.
2. Avant match : ajouter 2-3 observations shadow.
3. Apres closing : remplir `manual_closing_import.csv`.
4. Apres resultats : remplir `manual_results_import.csv`.
5. Soir : relancer `report_runner.py --ops --skip-dashboard`.
6. Lire `evidence_gate.html`.
7. Continuer la collecte si le statut est non valide.

## Ajout V8.3 : snapshots de cotes

Routine supplementaire pour juin :

1. Generer `reports/manual_odds_snapshot_template.csv`.
2. Renseigner quelques cotes observees avec timestamp.
3. Importer vers `reports/odds_snapshots.csv`.
4. Lire `odds_source_quality_report.py`.
5. Convertir en observations shadow seulement apres controle.
6. Noter un snapshot `is_near_close=true` si proche du coup d'envoi.
7. Matcher ce snapshot vers le ledger en dry-run.

Un snapshot near-close aide le diagnostic, mais ne remplace pas une vraie source closing historique documentee.
