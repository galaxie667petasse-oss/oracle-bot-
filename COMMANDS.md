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

## 10. Git workflow

```bash
git status --short
git diff
git add README.md PROJECT_STATUS.md COMMANDS.md project_audit.py external_xg_lab.py team_name_normalizer.py test_external_xg_lab.py test_team_name_normalizer.py docs/external_xg_integration_plan.md .gitignore
git commit -m "Prepare external xG integration lab V6.6"
```

Verifier avant commit qu'aucun fichier sensible n'est ajoute :

```bash
git ls-files -- oracle_db.json "oracle_db_backup_*.json" "oracle_db_archive_*.json" data external_data .env variable reports
```

## 11. Ce qu'il ne faut pas faire

- Ne pas modifier `main.py` ou `Dockerfile` sans bug bloquant prouve.
- Ne pas modifier `oracle_db.json`, les backups ou `data/MATCHES.csv` pour stabiliser la release.
- Ne pas lancer Railway maintenant.
- Ne pas rendre Telegram plus agressif.
- Ne pas utiliser les stats post-match pour predire le meme match.
- Ne pas transformer un edge validation ou un favori H2H fragile en pick conseille.
- Ne pas scraper FBref, Understat ou Kaggle automatiquement.
- Ne pas utiliser un preview xG comme dataset d'entrainement production.
