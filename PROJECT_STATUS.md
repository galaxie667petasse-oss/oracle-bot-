# Statut Oracle Football Bot

## Version actuelle

V8.0 Shadow Mode & Manual CLV Capture.

Etat : local prudent. V7.0 Statistical Proof Foundation, V7.2 Understat xG Full Pipeline Quality Gate, V7.3 Multi-League Join Diagnostics, V7.4 Bundesliga Team Alias Expansion, V7.5 Big Five xG Aggregation, V7.6 Closing Odds Recovery, V7.7 Partial CLV Pipeline et V7.8 Closing Column Forensics restent en place. V8.0 ajoute un mode shadow local pour collecter des observations live et des closing odds manuelles. Aucun signal robuste active. Aucun changement V8.0 ne branche Telegram, Railway ou un pick automatique.

## Etat general

- Memoire moderne recommandee : 2015-2025.
- Volume connu : environ 528066 records regles.
- Feature matrix principale : `data/features_modern.csv`.
- Rapports locaux disponibles : backtest, favoris, stabilite, pricing, ML, External Dataset Lab, dashboard central.
- Probe Understat multi-saisons disponible, dependance `soccerdata` optionnelle.
- Export Understat EPL 2020-2025 attendu : 1900 lignes avec saisons explicites `2020-2021` a `2024-2025`.
- Quality gate xG disponible via `xg_dataset_quality.py`.
- Diagnostic jointure disponible via `join_diagnostics.py`.
- Alias Bundesliga, Serie A et Ligue 1 disponibles dans `team_name_normalizer.py`.
- Pipeline local Understat xG disponible via `understat_xg_pipeline.py`.
- Agregateur multi-ligue Big 5 disponible via `multi_league_xg_aggregator.py`.
- Rapport CLV readiness disponible via `clv_readiness_report.py`.
- Probe closing odds disponible via `closing_odds_probe.py`, lecture seule.
- Closing column forensics disponible : min/max/mediane/percentiles, exemples bruts, taux de valeurs plausibles et verdict par colonne.
- Shadow ledger local disponible via `shadow_ledger.py`.
- Import closing manuel disponible via `closing_manual_import.py`.
- Rapport CLV shadow disponible via `shadow_clv_report.py`.
- Candidats shadow quotidiens disponibles via `daily_shadow_candidates.py`.
- Preview features closing disponible via `features_closing_enricher.py`, sortie limitee a `reports/`.
- CLV partielle H2H home/away disponible uniquement si la closing exacte du cote joue existe.
- CLV / Closing Line Value disponible si des cotes closing sont presentes.
- Reliability curves disponibles via `calibration_report.py`.
- Validation statistique disponible via `statistical_validation.py`.
- Benchmark gouvernance V8.0 disponible.
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
- Bundesliga exportait correctement mais jointait trop faiblement a xgabora avant alias, ce qui justifiait le blocage strict ;
- Serie A est exportee localement chez l'utilisateur et doit etre relancee apres alias Parma si le CSV est present ;
- Ligue 1 doit encore etre exportee et diagnostiquee manuellement ;
- CLV readiness confirme que les colonnes closing fiables restent le passage oblige ;
- `data/MATCHES.csv` doit etre inspecte en lecture seule pour savoir si des closing odds fiables existent ;
- `C_LTH/C_LTA` ne couvrent pas draw, totals ou BTTS ;
- une CLV partielle ne valide pas une strategie globale ;
- absence de validation humaine complete.

## Etat des modules

- `understat_probe.py` : export optionnel Understat local via soccerdata, chemins `Path`, dry-run sans reseau.
- `xg_dataset_quality.py` : controle lignes, saisons, completeness, xG coverage, doublons et fuite.
- `join_diagnostics.py` : join rate avant/apres alias, fuzzy suggestions, causes probables et join_quality.
- `team_name_normalizer.py` : alias manuels controles, dont La Liga, Bundesliga, Serie A et Ligue 1, sans modification des CSV source.
- `understat_xg_pipeline.py` : orchestration locale quality, jointure, rolling features, xG model et gouvernance optionnelle.
- `multi_league_xg_aggregator.py` : synthese Big 5 des rapports xG existants, sans recuperation reseau.
- `closing_odds_probe.py` : inspection lecture seule du CSV source pour colonnes closing H2H, total et BTTS, avec profil forensique des valeurs.
- `features_closing_enricher.py` : preview dans `reports/` pour joindre features actuelles et colonnes closing source, avec `clv_available/clv_reason`, sans ecrire dans `data/`.
- `clv_readiness_report.py` : inspection des colonnes closing manquantes, avec distinction calculable maintenant/apres enrichissement/dans preview, sans inventer de CLV.
- `clv_analysis.py` : CLV descriptive, accepte la preview partielle et exclut les lignes sans closing exacte.
- `calibration_report.py` : Brier, log loss, ECE, MCE et reliability curves.
- `statistical_validation.py` : IC ROI, bootstrap, Monte Carlo, drawdown, sample size et Benjamini-Hochberg.
- `decision_policy.py` : gates CLV/calibration/statistiques/multiple testing.
- `benchmark_governance.py` : registre enrichi V8.0 avec CLV, shadow report, nulls prudents et warnings si metriques absentes.
- `report_runner.py` : mode `--statistical`.
- `dashboard_builder.py` : sections CLV, calibration, validation statistique, multiple testing et gouvernance finale.
- `shadow_ledger.py` : journal local des observations shadow dans `reports/`.
- `closing_manual_import.py` : import manuel de closing odds par `shadow_id`.
- `shadow_clv_report.py` : rapport CLV/ROI shadow, observation seulement.
- `daily_shadow_candidates.py` : preparation de candidats shadow depuis CSV live ou historique, sans conseil de pari.

## Resultats connus

- 67 strategies/modeles ont ete evalues dans l'etat precedent.
- Meilleur score historique observe : 79/100.
- Candidats robustes : 0.
- Observations H2H favoris : watchlist seulement.
- xG EPL 2024-2025 : echantillon trop petit, pas de signal robuste.
- Ancien export Understat 1520 lignes : incomplet a cause d'une ambiguite de saison.
- Nouvel export Understat attendu 1900 lignes : base correcte pour un laboratoire EPL 2020-2025.
- EPL Understat 2020-2025 : jointure autour de 98%, quality exploitable, mais xG ne bat pas le marche.
- La Liga Understat 2020-2025 : export complet, jointure avant alias autour de 39.89%, apres alias autour de 99.89%, observation seulement.
- Bundesliga Understat 2020-2025 : export complet 1530 matchs, cinq saisons de 306 matchs, xG coverage 100%, jointure initiale autour de 24.12% avant alias et autour de 99.93% apres alias.
- Serie A Understat 2020-2025 : export utilisateur observe a 1900 matchs, cinq saisons completes, xG coverage 100%, jointure apres alias observee a 95.79% avant correction Parma ; `Parma Calcio 1913` est maintenant mappe vers `Parma`.
- Ligue 1 : aliases prets, export a lancer manuellement.
- CLV sur `data/features_modern.csv` est probablement indisponible tant que les colonnes closing `C_*` ne sont pas exportees.
- `data/MATCHES.csv` contient des colonnes `C_LTH/C_LTA` detectees par nom, mais V7.8 les a rejetees comme valeurs non plausibles pour des cotes decimales.
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
- Diagnostic de jointure sans recuperation reseau.
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

1. Commit/push la phase locale V8.0.
2. Utiliser `shadow_ledger.py --init` puis ajouter les observations shadow des matchs de juin.
3. Importer les closing odds manuelles fiables avec `closing_manual_import.py`.
4. Lancer manuellement Ligue 1, puis `join_diagnostics.py --league "Ligue 1"` et le pipeline strict.
5. Relancer `multi_league_xg_aggregator.py`.
6. Relire `shadow_clv_report.py` avec sample, coverage et CLV moyenne.
7. Sinon chercher une source closing complete fiable.
