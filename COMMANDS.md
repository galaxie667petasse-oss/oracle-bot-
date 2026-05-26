# Commandes Oracle Football Bot

Ce fichier sert de pense-bete local pour tester, auditer et comprendre le projet. Les commandes ci-dessous ne doivent pas rendre le bot plus agressif et ne doivent pas transformer un signal fragile en pick conseille.

## 1. Setup local

```bash
python --version
pip install -r requirements.txt
```

Pour le ML local, `numpy` est requis. `sklearn` reste optionnel : si absent, `model_trainer.py` ignore proprement random forest et gradient boosting.

## 2. Tests

```bash
python -m compileall -q .
python test_pricing.py
python test_feature_builder.py
python test_model_trainer.py
python test_backtest_evaluator.py
python test_report_runner.py
python test_project_audit.py
python test_decision_policy.py
python test_benchmark_governance.py
python test_understat_probe.py
python test_clv_analysis.py
python test_calibration_report.py
python test_statistical_validation.py
python project_audit.py
```

Tests additionnels utiles :

```bash
python test_xgabora_dataset_import.py
python test_external_dataset_probe.py
python test_external_join_plan.py
```

## 3. Import dataset moderne

Inspecter les dates sans modifier la memoire :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --inspect-dates
```

Importer la periode moderne recommandee :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --from 2015-01-01 --to 2025-12-31
```

Ne jamais modifier `data/MATCHES.csv` pour ajuster un resultat.

## 4. Generation features

```bash
python feature_builder.py --output data/features_modern.csv
```

La feature matrix ne modifie pas `oracle_db.json`. Les post-match features sont marquees pour analyse et exclues par defaut du modele.

## 5. Backtest

```bash
python backtest_evaluator.py --preset modern
python backtest_evaluator.py --favorite-report
python backtest_evaluator.py --stability-report
python backtest_evaluator.py --pricing-report
```

Un rapport negatif est une information utile : il confirme qu'il faut rester strict.

## 6. ML

```bash
python model_trainer.py --features data/features_modern.csv
python model_trainer.py --features data/features_modern.csv --market h2h
python model_trainer.py --features data/features_modern.csv --market total
```

Analyse volontairement non predictive avec stats finales du match :

```bash
python model_trainer.py --features data/features_modern.csv --allow-post-match-features
```

Cette option ne doit jamais servir a valider un modele live.

## 7. Rapports

Rapport rapide :

```bash
python report_runner.py --quick
python dashboard_builder.py --latest
```

Rapport complet :

```bash
python report_runner.py --full
python dashboard_builder.py --latest
```

Le rapport genere `reports/oracle_YYYY_MM_DD_HHMMSS/index.html` et `summary.json`.

## 8. External dataset lab

```bash
python external_dataset_probe.py --profile-csv data/features_modern.csv
python external_dataset_probe.py --list
python external_dataset_probe.py --profile-csv chemin/vers/fichier.csv
python external_dataset_probe.py --profile-folder chemin/vers/dossier
python external_dataset_probe.py --recommend chemin/vers/fichier.csv
python external_join_plan.py --xgabora data/features_modern.csv --external chemin/vers/fichier.csv
python external_adapters/epl_fbref_lab.py --profile chemin/vers/dossier
```

Le lab externe profile des donnees fournies localement. Il ne telecharge rien, ne scrape rien et n'influence aucun pick.

## 9. External xG Integration Lab

Ces commandes sont a lancer plus tard, seulement apres avoir fourni manuellement un dataset externe local. Elles ne telechargent rien, ne scrape rien et ne branchent aucun signal aux picks.

Profiler un dataset xG :

```bash
python external_xg_lab.py --profile external_data/epl_fbref_2024_2025
```

Tester la jointure xgabora/date/equipes :

```bash
python external_xg_lab.py --join-plan --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv
python external_xg_lab.py --evaluate-join --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv
```

Generer un preview controle dans `reports/` :

```bash
python external_xg_lab.py --build-preview --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv --output reports/external_xg_preview.csv
```

Le preview ne sert pas a entrainer le bot. Le xG final doit etre transforme en rolling features pre-match avant tout test predictif.

## 10. External xG Rolling Features Lab

Generer les rolling xG pre-match depuis le dataset externe fourni manuellement :

```bash
python external_xg_features.py --external external_data/epl_fbref_2024_2025/pl_24-25_matches_clean.csv --xgabora data/features_modern.csv --output reports/epl_xg_rolling_features.csv
```

Evaluer le CSV enrichi :

```bash
python xg_model_lab.py --features reports/epl_xg_rolling_features.csv
```

Relancer la gouvernance avec le lab xG :

```bash
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/epl_xg_rolling_features.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Le fichier produit reste dans `reports/`. Il ne doit pas etre deplace dans `data/` ni utilise comme source de picks.

## 11. Understat Multi-Season Data Probe

Verifier si `soccerdata` est installe :

```bash
python understat_probe.py --check
```

Installer la dependance optionnelle :

```bash
python -m pip install soccerdata
```

Dry-run sans recuperation :

```bash
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv --dry-run
```

Commande reelle a lancer manuellement :

```bash
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv
python understat_probe.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
```

Pipeline ensuite :

```bash
python external_xg_lab.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
python external_xg_lab.py --evaluate-join --xgabora data/features_modern.csv --external external_data/understat_probe/epl_2020_2024_matches.csv
python external_xg_features.py --external external_data/understat_probe/epl_2020_2024_matches.csv --xgabora data/features_modern.csv --output reports/understat_xg_rolling_features.csv
python xg_model_lab.py --features reports/understat_xg_rolling_features.csv
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/understat_xg_rolling_features.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Understat reste laboratoire. xgabora reste la base betting principale.

## 12. Statistical Proof Foundation V7.0

Ces commandes mesurent la preuve statistique sans activer Telegram, sans Railway et sans modification DB.

Verifier Understat :

```bash
python understat_probe.py --check
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv
python understat_probe.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
```

Pipeline Understat vers xG rolling :

```bash
python external_xg_lab.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
python external_xg_features.py --external external_data/understat_probe/epl_2020_2024_matches.csv --xgabora data/features_modern.csv --output reports/understat_xg_rolling_features.csv
python xg_model_lab.py --features reports/understat_xg_rolling_features.csv
```

CLV, reliability curves et validation statistique :

```bash
python clv_analysis.py --features data/features_modern.csv --output reports/clv_report.json --html reports/clv_report.html
python calibration_report.py --features data/features_modern.csv --prob-column no_vig_probability --output reports/calibration_report.json --html reports/calibration_report.html
python statistical_validation.py --features data/features_modern.csv --output reports/statistical_validation.json --html reports/statistical_validation.html
python report_runner.py --statistical
python benchmark_governance.py --features data/features_modern.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Lecture prudente :

- ROI positif court terme ne suffit pas.
- CLV positive est prioritaire sur le ROI court terme.
- 1000 picks peuvent rester insuffisants si l'IC contient 0.
- Multiple testing transforme facilement une observation en faux positif.
- Kelly ne cree pas d'edge et reste limite a la simulation.
- Telegram et Railway attendent une validation complete.

## 13. V7.2 Understat xG Full Pipeline Quality Gate

Export Understat propre, avec saisons explicites pour eviter l'ambiguite `2021` :

```bash
python understat_probe.py --league EPL --seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output external_data/understat_probe/epl_2020_2025_matches.csv
```

Profil :

```bash
python understat_probe.py --profile external_data/understat_probe/epl_2020_2025_matches.csv
```

Quality gate :

```bash
python xg_dataset_quality.py --external external_data/understat_probe/epl_2020_2025_matches.csv --league EPL --expected-seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output reports/understat_epl_2020_2025_quality.json --html reports/understat_epl_2020_2025_quality.html
```

Pipeline :

```bash
python understat_xg_pipeline.py --external external_data/understat_probe/epl_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix understat_epl_2020_2025
```

Modele seul :

```bash
python xg_model_lab.py --features reports/understat_epl_2020_2025_rolling_features.csv --output reports/understat_epl_2020_2025_xg_model.json --html reports/understat_epl_2020_2025_xg_model.html
```

Benchmark :

```bash
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/understat_epl_2020_2025_rolling_features.csv --xg-quality reports/understat_epl_2020_2025_quality.json --xg-model reports/understat_epl_2020_2025_xg_model.json --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Report runner :

```bash
python report_runner.py --xg-understat
```

Le nouvel export 1900 lignes remplace l'ancien export 1520 lignes pour le laboratoire EPL 2020-2025. Le xG reste post-match et doit passer par rolling anti-fuite. Sans CLV positive et ROI test positif, aucune promotion n'est autorisee.

## 14. Scientific Benchmark & Model Governance

Benchmark complet si `data/features_modern.csv` est disponible :

```bash
python benchmark_governance.py --features data/features_modern.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Sorties :

- `model_registry.json` : registre versionne des strategies/modeles evalues ;
- `reports/benchmark_summary.json` : resume machine lisible ;
- `reports/benchmark_governance.html` : rapport local ouvrable dans le navigateur.

Le benchmark attribue un score prudent et une decision : rejected, watchlist, observation, candidate, active_shadow_only, active_decision_support ou production_allowed. Meme `production_allowed` ne signifie jamais pari automatique. Rien n'est branche aux picks Telegram.

## 15. Git workflow

```bash
git status --short
git diff
git add README.md PROJECT_STATUS.md COMMANDS.md docs/model_promotion_policy.md docs/external_xg_integration_plan.md understat_probe.py clv_analysis.py calibration_report.py statistical_validation.py decision_policy.py benchmark_governance.py report_runner.py dashboard_builder.py project_audit.py test_understat_probe.py test_clv_analysis.py test_calibration_report.py test_statistical_validation.py test_decision_policy.py test_benchmark_governance.py test_project_audit.py
git commit -m "Add statistical proof foundation V7.0"
```

Verifier avant commit qu'aucun fichier sensible n'est ajoute :

```bash
git ls-files -- oracle_db.json "oracle_db_backup_*.json" "oracle_db_archive_*.json" data external_data .env variable reports
```

## 16. Ce qu'il ne faut pas faire

- Ne pas modifier `main.py` ou `Dockerfile` sans bug bloquant prouve.
- Ne pas modifier `oracle_db.json`, les backups ou `data/MATCHES.csv` pour stabiliser la release.
- Ne pas lancer Railway maintenant.
- Ne pas rendre Telegram plus agressif.
- Ne pas utiliser les stats post-match pour predire le meme match.
- Ne pas transformer un edge validation ou un favori H2H fragile en pick conseille.
- Ne pas scraper FBref, Understat ou Kaggle automatiquement.
- Ne pas utiliser un preview xG comme dataset d'entrainement production.
- Ne pas promouvoir une strategie sans test 2024+ positif et gouvernance OK.
- Ne pas utiliser `home_xg` ou `away_xg` directs du match courant comme features predictives.
- Ne pas lancer une recuperation Understat large sans dry-run et sans limite de saisons.
