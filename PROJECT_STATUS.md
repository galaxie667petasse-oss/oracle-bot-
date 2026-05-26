# Statut Oracle Football Bot

## Version actuelle

V7.2 Understat xG Full Pipeline Quality Gate.

Etat : local prudent. V7.0 Statistical Proof Foundation reste en place et V7.2 ajoute un quality gate complet pour l'export Understat xG multi-saisons. Aucun signal robuste active. Aucun changement V7.2 ne branche Telegram, Railway ou un pick automatique.

## Etat general

- Memoire moderne recommandee : 2015-2025.
- Volume connu : environ 528066 records regles.
- Feature matrix principale : `data/features_modern.csv`.
- Rapports locaux disponibles : backtest, favoris, stabilite, pricing, ML, External Dataset Lab, dashboard central.
- Probe Understat multi-saisons disponible, dependance `soccerdata` optionnelle.
- Export Understat EPL 2020-2025 attendu : 1900 lignes avec saisons explicites `2020-2021` a `2024-2025`.
- Quality gate xG disponible via `xg_dataset_quality.py`.
- Pipeline local Understat xG disponible via `understat_xg_pipeline.py`.
- CLV / Closing Line Value disponible si des cotes closing sont presentes.
- Reliability curves disponibles via `calibration_report.py`.
- Validation statistique disponible via `statistical_validation.py`.
- Benchmark gouvernance V7.0 disponible.
- Aucun signal robuste active et aucun candidat robuste sans CLV positive.
- Railway/Telegram toujours en attente.

## Vrai blocage

Le vrai blocage n'est pas le bankroll management. Le blocage est :

- CLV absente ou non prouvee sur les strategies ;
- preuve statistique insuffisante ;
- bootstrap ROI 5e percentile souvent non valide ;
- multiple testing dangereux sur des dizaines de segments ;
- CLV + preuve statistique + stabilite annuelle restent necessaires meme si xG ameliore Brier/log loss ;
- xG multi-saisons Understat doit etre transforme en rolling pre-match sans fuite ;
- absence de validation humaine complete.

## Etat des modules

- `understat_probe.py` : export optionnel Understat local via soccerdata, chemins `Path`, dry-run sans reseau.
- `xg_dataset_quality.py` : controle lignes, saisons, completeness, xG coverage, doublons et fuite.
- `understat_xg_pipeline.py` : orchestration locale quality, jointure, rolling features, xG model et gouvernance optionnelle.
- `clv_analysis.py` : CLV descriptive, verdict indisponible si cotes closing absentes.
- `calibration_report.py` : Brier, log loss, ECE, MCE et reliability curves.
- `statistical_validation.py` : IC ROI, bootstrap, Monte Carlo, drawdown, sample size et Benjamini-Hochberg.
- `decision_policy.py` : gates CLV/calibration/statistiques/multiple testing.
- `benchmark_governance.py` : registre enrichi V7.0 avec nulls et warnings si metriques absentes.
- `report_runner.py` : mode `--statistical`.
- `dashboard_builder.py` : sections CLV, calibration, validation statistique, multiple testing et gouvernance finale.

## Resultats connus

- 67 strategies/modeles ont ete evalues dans l'etat precedent.
- Meilleur score historique observe : 79/100.
- Candidats robustes : 0.
- Observations H2H favoris : watchlist seulement.
- xG EPL 2024-2025 : echantillon trop petit, pas de signal robuste.
- Ancien export Understat 1520 lignes : incomplet a cause d'une ambiguite de saison.
- Nouvel export Understat attendu 1900 lignes : base correcte pour un laboratoire EPL 2020-2025.
- CLV sur `data/features_modern.csv` est probablement indisponible tant que les colonnes closing `C_*` ne sont pas exportees.
- Rien n'est branche aux picks Telegram ou Railway.

## Ce qui est valide

- Import historique massif local.
- Pricing no-vig descriptif.
- Backtest train/validation/test.
- Feature matrix locale reproductible.
- Exclusion par defaut des post-match features.
- Rolling features pre-match sans usage du match courant.
- Understat probe sans recuperation dans les tests.
- Quality gate Understat xG sans recuperation reseau.
- Pipeline xG local depuis CSV deja telecharge.
- Rapports locaux qui ne modifient pas `oracle_db.json`.
- Registre modele sans secrets, sans predictions individuelles et sans gros dataset.

## Ce qui reste invalide ou non confirme

- Transformer un ROI court terme en pick conseille.
- Promouvoir un signal sans CLV positive.
- Promouvoir un signal si la correction multiple testing echoue.
- Promouvoir un signal si le bootstrap ROI p05 est inferieur ou egal a 0.
- Utiliser Kelly comme preuve d'edge.
- Considerer Telegram ou Railway comme etape de validation.
- Utiliser `home_xg` ou `away_xg` du match courant comme features predictives.
- Considerer `production_allowed` comme pari automatique.

## Prochaine vraie priorite

1. Auditer l'export Understat EPL 2020-2025 avec `xg_dataset_quality.py`.
2. Lancer `understat_xg_pipeline.py --skip-benchmark` depuis le CSV local.
3. Comparer marche no-vig, modele sans xG et modele avec rolling xG.
4. Relancer CLV, calibration, statistical validation et benchmark governance.
5. Conserver Railway et Telegram en attente tant qu'aucune preuve robuste complete n'existe.
