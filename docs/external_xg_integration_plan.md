# Plan d'integration xG externe

## Objectif

La phase V6.6 prepare un laboratoire local pour profiler, joindre et evaluer un dataset externe riche en xG. Elle ne branche aucune source au bot, ne modifie pas `oracle_db.json`, ne modifie pas `data/MATCHES.csv` et ne peut pas influencer Telegram.

## Pourquoi le xG final est post-match

Le xG final d'un match est calcule a partir des tirs reels du match. Il n'est donc connu qu'apres ou pendant le match. L'utiliser pour predire ce meme match creerait une fuite de donnees : le modele verrait une information impossible a connaitre avant le coup d'envoi.

Sont post-match pour le match courant :

- xG final et xGA final ;
- tirs finaux et tirs cadres finaux ;
- score final et score mi-temps ;
- corners, cartons et evenements observes ;
- lineups finales si elles ne sont pas horodatees avant match.

## Transformation en rolling features pre-match

La bonne direction consiste a convertir les stats externes en moyennes historiques disponibles avant le match :

- `home_xg_avg5_before_match`
- `home_xga_avg5_before_match`
- `away_xg_avg5_before_match`
- `away_xga_avg5_before_match`
- `xg_diff_avg5_before_match`

Pour un match donne, ces colonnes doivent utiliser uniquement les matchs precedents de chaque equipe. Le match courant et tous les matchs futurs doivent etre exclus.

La phase V6.8 implemente cette direction avec `external_xg_features.py`. Le script exporte dans `reports/` des colonnes comme :

- `home_xg_for_avg3`
- `home_xg_for_avg5`
- `home_xg_against_avg3`
- `home_xg_against_avg5`
- `away_xg_for_avg3`
- `away_xg_for_avg5`
- `away_xg_against_avg3`
- `away_xg_against_avg5`
- `xg_diff_avg3`
- `xg_diff_avg5`

Les colonnes directes `home_xg` et `away_xg` du match courant ne sont pas exportees comme features predictives.

## Eviter la fuite de donnees

Regles minimales :

1. Trier les matchs par date.
2. Calculer les moyennes d'une equipe avant d'ajouter le match courant a son historique.
3. Traiter prudemment les matchs d'une meme date pour eviter qu'un match du matin alimente un match du soir si l'heure fiable manque.
4. Garder les colonnes post-match brutes dans un espace laboratoire, jamais dans les features live par defaut.
5. Refaire les splits train 2015-2022, validation 2023 et test 2024+ apres enrichissement.

## Test train/validation/test

Une source externe ne vaut le coup que si elle ameliore la probabilite sans fuite :

- train : apprendre les transformations et le modele ;
- validation : choisir eventuellement un seuil d'edge ;
- test 2024+ : verifier sans ajuster ;
- comparer au marche no-vig ;
- surveiller Brier score, log loss, calibration, ROI, drawdown et volume.

Un signal validation positif mais test negatif reste invalide.

## Statistical Proof Foundation V7.0

Apres generation de rolling xG pre-match, la source doit passer la couche V7.0 :

- CLV positive si le signal selectionne des cotes ;
- reliability curves lisibles avec Brier, log loss, ECE et MCE ;
- bootstrap ROI avec percentile 5% strictement positif ;
- intervalle de confiance ROI qui ne contient pas 0 pour un candidat ;
- correction de multiple testing si plusieurs segments xG sont compares ;
- aucun seuil choisi sur le test.

Un ROI xG positif sur un petit echantillon reste observation. Un sample inferieur a 300 est preuve insuffisante. Un sample inferieur a 1000 reste observation maximum.

## Decision d'integration

La source est interessante si :

- le taux de jointure est suffisamment eleve ;
- les dates et equipes sont fiables ;
- la periode couvre assez de matchs recents, notamment 2024+ ;
- le xG peut etre transforme en rolling pre-match ;
- l'amelioration bat le marche no-vig sur test ;
- le volume test est suffisant, idealement au moins 300 matchs.

La source est fragile si :

- le taux de jointure est inferieur a 50% ;
- les noms d'equipes demandent trop de corrections manuelles ;
- les dates ne sont pas fiables ;
- le dataset couvre une seule saison ou une seule ligue avec peu de matchs test.

## Pourquoi xgabora reste la base principale

xgabora/features reste la base principale tant que le dataset externe n'a pas de cotes fiables. Les cotes sont necessaires pour mesurer la baseline marche, le no-vig, l'edge, l'EV et le ROI.

Un dataset xG sans cotes peut enrichir xgabora ou servir de laboratoire, mais il ne remplace pas la base principale.

## Commandes futures

Quand un dataset externe sera fourni manuellement :

```bash
python external_xg_lab.py --profile external_data/epl_fbref_2024_2025
python external_xg_lab.py --evaluate-join --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv
python external_xg_lab.py --build-preview --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv --output reports/external_xg_preview.csv
```

Ces commandes restent locales. Elles ne telechargent rien et ne generent aucun pick.

## Commandes rolling xG V6.8

Dataset EPL 2024-2025 teste localement :

- dossier : `external_data/epl_fbref_2024_2025`
- fichier : `pl_24-25_matches_clean.csv`
- volume : 380 matchs
- periode : 2024-08-16 -> 2025-05-25
- jointure observee : environ 89.47%
- matchs joints avec xG + odds xgabora : environ 340

Generer les rolling features :

```bash
python external_xg_features.py --external external_data/epl_fbref_2024_2025/pl_24-25_matches_clean.csv --xgabora data/features_modern.csv --output reports/epl_xg_rolling_features.csv
```

Evaluer le laboratoire :

```bash
python xg_model_lab.py --features reports/epl_xg_rolling_features.csv
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/epl_xg_rolling_features.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Si l'echantillon test est inferieur a 300 ou si le ROI test est negatif, le signal reste observation seulement ou invalide. Une seule saison EPL ne suffit pas a generaliser a tout le bot.

## Understat multi-saisons V6.9

Le dataset EPL 2024-2025 a valide le pipeline, mais son volume reste limite. La prochaine piste est Understat multi-saisons via la dependance optionnelle `soccerdata`.

Pourquoi Understat :

- xG disponible sur plusieurs saisons ;
- couverture utile sur EPL, La Liga, Bundesliga, Serie A et Ligue 1 ;
- integration Python possible via DataFrames ;
- compatible avec le pipeline rolling xG apres export CSV.

Pourquoi xgabora reste principal :

- Understat ne fournit pas les cotes betting ;
- le no-vig, l'edge, l'EV et le ROI ont besoin des cotes xgabora/Football-Data ;
- Understat ne doit servir qu'a enrichir les features pre-match.

Installer soccerdata si besoin :

```bash
python -m pip install soccerdata
```

Verifier l'environnement :

```bash
python understat_probe.py --check
```

Dry-run prudent :

```bash
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv --dry-run
```

Export reel, a lancer manuellement :

```bash
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv
python understat_probe.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
```

Pipeline apres export :

```bash
python external_xg_lab.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
python external_xg_features.py --external external_data/understat_probe/epl_2020_2024_matches.csv --xgabora data/features_modern.csv --output reports/understat_xg_rolling_features.csv
python xg_model_lab.py --features reports/understat_xg_rolling_features.csv
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/understat_xg_rolling_features.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Aucun signal Understat ne doit etre active sans rolling pre-match, test temporel, benchmark gouvernance et validation humaine.

## Understat multi-saisons V7.0

La prochaine priorite humaine est de produire un export Understat plus large puis de relancer toute la preuve statistique :

```bash
python understat_probe.py --check
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv
python understat_probe.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
python external_xg_features.py --external external_data/understat_probe/epl_2020_2024_matches.csv --xgabora data/features_modern.csv --output reports/understat_xg_rolling_features.csv
python xg_model_lab.py --features reports/understat_xg_rolling_features.csv
python report_runner.py --statistical
```

Railway et Telegram doivent attendre. Une source xG multi-saisons peut ameliorer la comprehension du match, mais elle ne remplace pas la preuve CLV/statistique et ne cree aucun pick automatique.

## V7.2 Understat xG Full Pipeline Quality Gate

V7.2 transforme l'export Understat corrige en pipeline qualite complet. L'ancien export de 1520 lignes ne couvrait que quatre saisons EPL completes, car la saison courte `2021` etait interpretee de facon ambigue par `soccerdata`. Les exports doivent maintenant utiliser des saisons explicites :

```bash
python understat_probe.py --league EPL --seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output external_data/understat_probe/epl_2020_2025_matches.csv
```

Le nouvel export attendu contient 1900 lignes pour EPL, soit cinq saisons de 380 matchs. Le quality gate verifie ensuite saisons attendues, saisons manquantes, completeness, doublons date/home/away, xG coverage, scores manquants, colonnes post-match et risque de fuite :

```bash
python xg_dataset_quality.py --external external_data/understat_probe/epl_2020_2025_matches.csv --league EPL --expected-seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output reports/understat_epl_2020_2025_quality.json --html reports/understat_epl_2020_2025_quality.html
```

Le pipeline local ne telecharge rien. Il part d'un CSV Understat deja present, genere les rolling features dans `reports/`, lance le modele xG si possible et garde la gouvernance en mode laboratoire :

```bash
python understat_xg_pipeline.py --external external_data/understat_probe/epl_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix understat_epl_2020_2025
```

Lecture prudente :

- xG final = post-match, donc interdit comme feature directe du match courant ;
- rolling xG anti-fuite obligatoire ;
- Brier/log loss legerement meilleurs = observation technique, pas edge jouable ;
- ROI test negatif invalide l'edge ;
- CLV absente bloque toute promotion ;
- Telegram et Railway restent en attente.

## V7.3 Multi-League Join Diagnostics

Un export peut etre complet sans etre exploitable pour modele. La Liga 2020-2025 illustre ce cas : 1900 matchs et xG coverage 100%, mais une jointure observee autour de 39.89% contre xgabora/features rend l'analyse modele insuffisante. Les causes probables sont les noms d'equipes, accents, alias Understat/xgabora, dates decalees, competition differente ou calendriers manquants.

Diagnostic :

```bash
python join_diagnostics.py --xgabora data/features_modern.csv --external external_data/understat_probe/laliga_2020_2025_matches.csv --output reports/laliga_join_diagnostics.json --html reports/laliga_join_diagnostics.html
```

Le rapport se lit ainsi :

- `join_rate_before_alias` : jointure stricte avant alias ;
- `join_rate_after_alias` : jointure stricte apres alias manuel controle ;
- `join_rate_fuzzy` : potentiel de rapprochement, jamais applique automatiquement si ambigu ;
- `top_alias_suggestions` : pistes a valider humainement ;
- `probable_causes` : nom equipe different, accent, abreviation, date decalee, competition differente, equipe manquante.

Les alias ne doivent pas etre appliques aveuglement : un mauvais alias peut relier deux matchs differents et creer une fuite ou un signal artificiel. La regle V7.3 bloque le modele si `join_quality=insuffisant`, c'est-a-dire sous 50%. Le mode strict du pipeline stoppe sous 75% :

```bash
python understat_xg_pipeline.py --external external_data/understat_probe/laliga_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix laliga_2020_2025 --skip-benchmark --strict-join
```

EPL a une jointure proche de 98% et reste le meilleur terrain de controle. La Liga doit d'abord passer le diagnostic et les alias avant d'etre modelisee. Les autres ligues attendent pour eviter d'empiler des erreurs de jointure et du multiple testing.

## V7.4 Bundesliga Team Alias Expansion

La Bundesliga a valide le quality gate dataset, mais pas la jointure initiale : 1530 matchs, cinq saisons completes de 306 matchs et xG coverage 100%, avec une jointure autour de 24.12% avant alias. Le blocage `--strict-join` etait donc le comportement attendu.

Les noms xgabora sont souvent raccourcis : `Leverkusen`, `Ein Frankfurt`, `MGladbach`, `Dortmund`, `FC Koln`, `Mainz`, `RB Leipzig`, `Werder Bremen`, `Union Berlin`, `Hertha`, `Schalke 04`. V7.4 ajoute les alias Bundesliga controles dans `team_name_normalizer.py`.

Relancer :

```bash
python join_diagnostics.py --xgabora data/features_modern.csv --external external_data/understat_probe/bundesliga_2020_2025_matches.csv --output reports/bundesliga_join_diagnostics.json --html reports/bundesliga_join_diagnostics.html --league Bundesliga
python understat_xg_pipeline.py --external external_data/understat_probe/bundesliga_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix bundesliga_2020_2025 --skip-benchmark --strict-join
```

Un dataset xG propre ne suffit jamais : la jointure doit etre excellente ou exploitable, puis le modele doit encore battre le marche, avoir un sample suffisant, une CLV positive et une gouvernance complete.

## V7.5 Big Five xG Completion & CLV Readiness

V7.5 prepare la fin du laboratoire Big Five sans lancer automatiquement Serie A ou Ligue 1. Les aliases Serie A et Ligue 1 sont ajoutes pour eviter de repeter les erreurs La Liga/Bundesliga : un export Understat peut etre complet, avec 100% xG, mais rester inutilisable si la jointure ne rejoint pas les noms xgabora reels.

Principes :

- EPL, La Liga et Bundesliga servent de controles multi-ligues ;
- Serie A et Ligue 1 doivent etre exportees manuellement, une ligue a la fois ;
- `join_diagnostics.py --league` doit confirmer la cible xgabora et les alias avant modeling ;
- `understat_xg_pipeline.py --strict-join` bloque sous 75% de jointure ;
- `multi_league_xg_aggregator.py` compare Brier/log loss, ROI edge, sample et blocages par ligue ;
- `clv_readiness_report.py` identifie les colonnes closing odds manquantes ;
- sans CLV fiable, tout xG reste observation/watchlist.

Commandes :

```bash
python understat_probe.py --league "Serie A" --seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output external_data/understat_probe/seriea_2020_2025_matches.csv
python join_diagnostics.py --xgabora data/features_modern.csv --external external_data/understat_probe/seriea_2020_2025_matches.csv --output reports/seriea_join_diagnostics.json --html reports/seriea_join_diagnostics.html --league "Serie A"
python understat_xg_pipeline.py --external external_data/understat_probe/seriea_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix seriea_2020_2025 --skip-benchmark --strict-join

python understat_probe.py --league "Ligue 1" --seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output external_data/understat_probe/ligue1_2020_2025_matches.csv
python join_diagnostics.py --xgabora data/features_modern.csv --external external_data/understat_probe/ligue1_2020_2025_matches.csv --output reports/ligue1_join_diagnostics.json --html reports/ligue1_join_diagnostics.html --league "Ligue 1"
python understat_xg_pipeline.py --external external_data/understat_probe/ligue1_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix ligue1_2020_2025 --skip-benchmark --strict-join

python multi_league_xg_aggregator.py --reports-dir reports --output reports/big5_xg_summary.json --html reports/big5_xg_summary.html
python clv_readiness_report.py --features data/features_modern.csv --output reports/clv_readiness.json --html reports/clv_readiness.html
```

Interpretation : une ligue peut afficher un ROI edge positif mais rester bloquee par sample < 1000 ou CLV absente. Une legere amelioration Brier/log loss est une observation technique, pas une preuve de rentabilite. Telegram et Railway restent hors scope.

## V7.6 Big Five Completion & Closing Odds Recovery

V7.6 ferme les trous d'alias observes apres les premieres executions Big Five. Serie A exporte proprement 1900 matchs avec 100% xG, mais `Parma Calcio 1913` restait une cause visible de non-jointure ; l'alias pointe maintenant vers `Parma`. Bundesliga garde les mappings longs/courts et couvre `St. Pauli` / `Holstein Kiel`. Ligue 1 est preparee avec des aliases plus explicites avant execution humaine.

La completion Big Five reste descriptive :

- `multi_league_xg_aggregator.py` signale les ligues disponibles, manquantes, exploitables et bloquees par CLV/sample/jointure ;
- Big Five incomplet produit une conclusion partielle ;
- Big Five complet sans CLV fiable produit toujours zero candidat robuste ;
- xG meilleur en Brier/log loss reste une observation technique si ROI test, sample ou CLV ne suivent pas.

La recuperation closing odds est volontairement separee du pipeline xG :

```bash
python closing_odds_probe.py --csv data/MATCHES.csv --output reports/closing_odds_probe.json --html reports/closing_odds_probe.html
python clv_readiness_report.py --features data/features_modern.csv --closing-probe reports/closing_odds_probe.json --output reports/clv_readiness.json --html reports/clv_readiness.html
python features_closing_enricher.py --features data/features_modern.csv --source data/MATCHES.csv --output reports/features_with_closing_preview.csv
```

`features_closing_enricher.py` ne doit jamais ecrire dans `data/`. Si les colonnes closing sont absentes ou douteuses, le projet reste un outil d'analyse prudent. Si elles existent, la prochaine etape est une preview verifiee, puis seulement ensuite une analyse CLV descriptive.

## V7.7 Partial CLV Pipeline

V7.7 exploite prudemment les colonnes `C_LTH` et `C_LTA` detectees dans la source locale. Le scope est volontairement limite :

- H2H home : possible avec `C_LTH` ;
- H2H away : possible avec `C_LTA` ;
- H2H draw : exclu si `C_LTD` manque ;
- totals et BTTS : exclus sans colonnes closing exactes.

Commandes locales sans reseau :

```bash
python closing_odds_probe.py --csv data/MATCHES.csv --output reports/closing_odds_probe.json --html reports/closing_odds_probe.html
python features_closing_enricher.py --features data/features_modern.csv --source data/MATCHES.csv --output reports/features_with_closing_preview.csv
python clv_analysis.py --features reports/features_with_closing_preview.csv --output reports/clv_partial_report.json --html reports/clv_partial_report.html
python clv_readiness_report.py --features data/features_modern.csv --closing-probe reports/closing_odds_probe.json --preview reports/features_with_closing_preview.csv --output reports/clv_readiness.json --html reports/clv_readiness.html
python report_runner.py --closing-preview --skip-benchmark
```

Interpretation : une CLV partielle positive sur H2H home/away peut creer une observation plus informative, mais pas une preuve globale. Elle doit etre lue avec coverage, sample, CLV positive rate, ROI test, bootstrap, calibration et multiple testing. Ligue 1 reste une execution humaine separee : aucune recuperation reseau n'est lancee par les tests.

## V7.8 Closing Column Forensics

La couche xG Big Five reste bloquee par la preuve CLV. V7.8 ajoute donc un diagnostic de colonnes closing avant toute nouvelle conclusion betting :

```bash
python closing_odds_probe.py --csv data/MATCHES.csv --sample-values --max-sample 50 --output reports/closing_odds_probe.json --html reports/closing_odds_probe.html
```

Le probe ne se contente pas du nom `C_*`. Il verifie les distributions, les exemples, les percentiles et la part des valeurs plausibles en cotes decimales. Si une colonne est detectee par nom mais non plausible, la preview closing doit la rejeter. Le xG peut rester utile pour calibration, mais sans closing fiable, il ne valide aucun edge betting.

## V8.0 Shadow Mode & Manual CLV Capture

Le Big Five xG complet peut produire des observations techniques, mais la preuve betting doit maintenant venir d'un suivi live propre. `shadow_ledger.py` enregistre les observations, `closing_manual_import.py` ajoute les closing odds manuelles et `shadow_clv_report.py` mesure la CLV shadow.

Ce mode ne lance aucune recuperation reseau et ne branche rien a Telegram. Il sert a accumuler un sample de matchs de juin, avec closing odds reelles, avant toute conclusion. Sample < 1000 ou CLV absente = observation seulement.

## V8.1 Shadow UX & Daily Workflow

V8.1 ne change pas le pipeline xG, mais il rend la collecte de preuve quotidienne plus exploitable :

- `shadow_workflow.py` initialise le ledger, genere les templates et relance le rapport ;
- `shadow_templates.py` fournit les CSV candidats, closing et resultats ;
- `results_manual_import.py` ajoute les resultats apres match ;
- `report_runner.py --daily-shadow` regenere le rapport evidence et la gouvernance locale.

Le lien avec xG reste prudent : une observation xG peut etre placee en shadow ledger, puis comparee a une closing odds manuelle. Sans CLV fiable, sans sample suffisant et sans stabilite, le xG reste une observation technique. Aucune mise, aucun Telegram et aucun Railway ne sont actives.

## V8.2 Operations Center

La couche V8.2 ne modifie pas les conclusions xG. Elle ajoute un controle operationnel autour des preuves :

- `shadow_quality_audit.py` verifie que le ledger shadow est propre ;
- `evidence_gate.py` bloque toute interpretation si Big 5, CLV ou shadow evidence sont insuffisants ;
- `sample_size_planner.py` rappelle le volume necessaire ;
- `shadow_simulator.py` permet de tester le pipeline sans vraie donnee.

Le Big 5 xG complet reste une force technique, mais sans CLV live/manuelle fiable il ne valide aucun edge.

## Lien avec V8.3 Odds Source Lab

V8.3 prepare la collecte de cotes qui manque au laboratoire xG :

- xG peut ameliorer legerement Brier/log loss ;
- l'edge betting reste non prouve sans CLV ;
- les snapshots de cotes doivent etre valides par marche et side ;
- les observations shadow restent separees de toute activation.

Cette couche ne change pas la conclusion : Big 5 xG reste observation technique tant que CLV, sample, ROI test et gouvernance complete ne convergent pas.
