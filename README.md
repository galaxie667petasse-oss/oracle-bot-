# Oracle Football Bot

## Vision du projet

Oracle Football Bot est un outil local d'analyse football et de controle statistique. Il aide a comprendre les marches, les cotes, les marges bookmaker, les backtests et les limites des signaux disponibles.

Ce n'est pas un bot magique de pronostics. La posture actuelle est prudente : si un signal ne survit pas au split train/validation/test, il reste une observation et ne devient pas une selection activee.

## Ce que le bot fait

- Charge une memoire locale de matchs et candidats regles.
- Importe un historique xgabora/Football-Data/ClubElo depuis un CSV local.
- Calcule les probabilites implicites, les probabilites no-vig, les marges marche et l'EV baseline.
- Construit une feature matrix locale avec features pre-match et rolling avg5.
- Exclut par defaut les stats post-match pour eviter la fuite de donnees.
- Lance des backtests temporels, rapports favoris, stabilite et pricing.
- Entraine un ML leger local pour mesurer une probabilite, pas pour generer des picks.
- Profile des datasets externes fournis localement, sans telechargement ni scraping.
- Produit des rapports CLV, reliability curves, bootstrap, Monte Carlo et multiple testing.
- Genere un rapport central local HTML/JSON pour audit.

## Ce que le bot ne fait pas

- Il ne garantit aucun profit.
- Il ne transforme pas un edge fragile en pick automatique.
- Il ne remplace pas xgabora par un dataset externe sans test.
- Il ne scrape pas FBref, Understat, Kaggle ou une autre source.
- Il n'appelle pas d'API pour les phases locales.
- Il ne doit pas rendre Telegram plus agressif.
- Il ne doit pas etre redeploye sur Railway tant qu'aucune strategie robuste positive n'est validee.

## Architecture

- `main.py` : point d'entree historique Telegram/Railway. Ne pas modifier sans bug bloquant prouve.
- `bot_app.py`, `bot_app_v52.py`, `telegram_ui.py` : couche Telegram historique.
- `pricing.py` : probabilites implicites, no-vig, marge marche, fair odds et EV.
- `xgabora_dataset_import.py` : import du CSV historique local et enrichissement des records.
- `feature_builder.py` : feature matrix locale, rolling pre-match, marquage post-match.
- `model_trainer.py` : regression logistique locale, modeles sklearn optionnels, edge simulation.
- `benchmark_governance.py` : benchmark scientifique, scoring de robustesse et registre modele.
- `decision_policy.py` : politique de classification/promotion sans dependance Telegram.
- `backtest_evaluator.py` : backtests et rapports modern/recent/favoris/stabilite/pricing.
- `external_dataset_probe.py` : profilage de CSV/dossiers externes.
- `external_join_plan.py` : plan de jointure theorique date/home/away sans ecriture.
- `external_xg_lab.py` : laboratoire xG externe, jointure controlee et preview local.
- `external_xg_features.py` : transformation du xG final externe en rolling features pre-match.
- `xg_model_lab.py` : evaluation locale descriptive des rolling xG.
- `xg_dataset_quality.py` : quality gate local pour auditer un CSV xG externe avant modeling.
- `join_diagnostics.py` : diagnostic multi-league join diagnostics et suggestions d'alias equipe.
- `understat_xg_pipeline.py` : orchestration locale Understat xG depuis un CSV deja telecharge.
- `understat_probe.py` : probe optionnel Understat multi-saisons via `soccerdata`.
- `clv_analysis.py` : mesure descriptive de Closing Line Value si des cotes closing sont disponibles.
- `calibration_report.py` : reliability curves, Brier, log loss, ECE et MCE.
- `statistical_validation.py` : bootstrap ROI, Monte Carlo, IC, drawdown et correction multiple testing.
- `team_name_normalizer.py` : normalisation prudente et suggestions de mapping d'equipes.
- `external_adapters/epl_fbref_lab.py` : adaptateur laboratoire EPL/FBref local.
- `report_runner.py` : orchestration des rapports locaux.
- `dashboard_builder.py` : generation de `index.html` et `summary.json`.
- `project_audit.py` : audit release candidate local.
- `model_registry.json` : metadonnees agregees des modeles/strategies evalues.

## Pipeline local

1. Verifier l'environnement et les fichiers sensibles.
2. Importer ou conserver la memoire moderne 2015-2025.
3. Generer `data/features_modern.csv`.
4. Lancer pricing, backtest, favorite-report et stability-report.
5. Lancer le ML leger uniquement comme mesure de probabilite.
6. Lancer la couche V7.0 Statistical Proof Foundation.
7. Lancer le quality gate V7.2 si un CSV Understat multi-saisons existe localement.
8. Generer le rapport central local.
9. Lire les conclusions avant toute decision Railway ou Telegram.

Commandes courtes :

```bash
python project_audit.py
python feature_builder.py --output data/features_modern.csv
python backtest_evaluator.py --preset modern
python model_trainer.py --features data/features_modern.csv
python clv_analysis.py --features data/features_modern.csv
python calibration_report.py --features data/features_modern.csv --prob-column no_vig_probability
python statistical_validation.py --features data/features_modern.csv
python report_runner.py --quick
python dashboard_builder.py --latest
```

## Memoire

La memoire recommandee est la periode moderne 2015-2025. Les donnees anciennes peuvent servir d'archive, mais elles ne doivent pas dominer une decision moderne.

- Sans `DATABASE_URL`, le projet lit `oracle_db.json`.
- Les scripts locaux forcent ou privilegient l'usage local quand c'est necessaire.
- Les rapports et builders ne doivent pas modifier `oracle_db.json`.
- Le test 2024+ reste la verification finale.

## Import historique

Inspecter les dates :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --inspect-dates
```

Importer la periode moderne :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --from 2015-01-01 --to 2025-12-31
```

L'importeur ignore les doublons via une cle stable. Ne pas modifier `data/MATCHES.csv` pour ameliorer artificiellement un resultat.

## Pricing

`pricing.py` fournit :

- `implied_probability`
- `fair_odds`
- `market_margin`
- `remove_vig_1x2`
- `remove_vig_two_way`
- `edge_probability`
- `expected_value`

Le pricing sert a mesurer le marche. Il ne cree jamais une cote absente et ne rend pas le bot plus agressif.

Rapport :

```bash
python backtest_evaluator.py --pricing-report
```

Resultat connu : les marges elevees sont dangereuses. Une marge faible ne suffit pas a rendre un pari jouable.

## Backtest

Le backtest se lit avec un split temporel. Le passe de train permet de construire une regle, la validation sert a choisir prudemment, et le test 2024+ sert de juge final.

```bash
python backtest_evaluator.py --preset modern
python backtest_evaluator.py --favorite-report
python backtest_evaluator.py --stability-report
python backtest_evaluator.py --pricing-report
```

Si aucune strategie n'est positive et stable sur test, la bonne conclusion est de ne pas jouer.

## ML

Le ML local mesure si une probabilite legere peut ameliorer la baseline marche no-vig. Il ne pilote pas Telegram et ne genere aucun pick.

```bash
python model_trainer.py --features data/features_modern.csv
python model_trainer.py --features data/features_modern.csv --market h2h
python model_trainer.py --features data/features_modern.csv --market total
```

`numpy` est requis pour le ML local. `sklearn` est optionnel : s'il est absent, random forest et gradient boosting sont ignores proprement.

Mesures principales :

- Brier score : plus bas est meilleur, mesure l'erreur de probabilite.
- Log loss : plus bas est meilleur, penalise les predictions trop confiantes.
- Calibration buckets : comparent probabilite predite et taux reel.
- Edge simulation : teste `model_probability - no_vig_probability` sans creer de pick automatique.

Les stats finales du match sont exclues par defaut. L'option suivante est seulement descriptive :

```bash
python model_trainer.py --features data/features_modern.csv --allow-post-match-features
```

## Rapports

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

Chaque execution cree un dossier `reports/oracle_YYYY_MM_DD_HHMMSS/` avec les sorties `.txt`, `index.html` et `summary.json`. Le rapport est descriptif et ne declenche aucun pick.

## External Dataset Lab

Le lab externe sert a profiler une source locale plus riche, par exemple xG, xGA, tirs, tirs cadres, lineups, stats joueurs/equipes et resultats.

```bash
python external_dataset_probe.py --list
python external_dataset_probe.py --profile-csv chemin/vers/fichier.csv
python external_dataset_probe.py --profile-folder chemin/vers/dossier
python external_dataset_probe.py --recommend chemin/vers/fichier.csv
python external_join_plan.py --xgabora data/features_modern.csv --external chemin/vers/fichier.csv
```

Un dataset sans cotes mais riche en xG ne remplace pas xgabora. Il peut enrichir un laboratoire, puis seulement etre evalue en train/validation/test.

## External xG Integration Lab

La phase V6.6 prepare un laboratoire d'integration xG externe. Elle ne telecharge aucun dataset, n'appelle pas Kaggle, ne scrape aucun site, ne modifie pas `oracle_db.json` et ne branche rien aux picks Telegram.

Objectif :

- profiler un CSV ou dossier externe fourni manuellement ;
- detecter date, equipes, scores, xG/xGA, tirs, tirs cadres, lineups et stats joueurs/equipes ;
- tester une jointure theorique avec xgabora/features ;
- generer un petit preview dans `reports/` pour verifier la jointure ;
- documenter comment transformer le xG final en rolling features pre-match.

Commandes futures, quand un dataset externe sera disponible localement :

```bash
python external_xg_lab.py --profile external_data/epl_fbref_2024_2025
python external_xg_lab.py --evaluate-join --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv
python external_xg_lab.py --build-preview --xgabora data/features_modern.csv --external external_data/epl_fbref_2024_2025/matches.csv --output reports/external_xg_preview.csv
```

Le preview ne sert pas a entrainer le bot. Il sert uniquement a verifier les colonnes et la jointure. Le xG final du match est post-match : il doit etre transforme en rolling features comme `home_xg_avg5_before_match` avant toute evaluation predictive.

Les details sont dans `docs/external_xg_integration_plan.md`.

## External xG Rolling Features Lab

La phase V6.8 transforme un dataset xG externe post-match en features rolling pre-match. Le xG final du match courant reste interdit comme feature directe : seules les moyennes calculees sur les matchs precedents sont exportees.

Generation du CSV laboratoire :

```bash
python external_xg_features.py --external external_data/epl_fbref_2024_2025/pl_24-25_matches_clean.csv --xgabora data/features_modern.csv --output reports/epl_xg_rolling_features.csv
```

Colonnes principales ajoutees :

- `home_xg_for_avg3`, `home_xg_for_avg5`
- `home_xg_against_avg3`, `home_xg_against_avg5`
- `away_xg_for_avg3`, `away_xg_for_avg5`
- `away_xg_against_avg3`, `away_xg_against_avg5`
- `xg_diff_avg3`, `xg_diff_avg5`
- tendances 3 vs 5 et nombre de matchs disponibles

Evaluation descriptive :

```bash
python xg_model_lab.py --features reports/epl_xg_rolling_features.csv
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/epl_xg_rolling_features.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Le dataset EPL 2024-2025 couvre une seule ligue et une seule saison. Meme avec une bonne jointure, il reste laboratoire seulement : l'echantillon test peut etre faible, les resultats ne generalisent pas automatiquement, et xgabora reste la base principale car il contient les cotes et le volume historique.

Le rapport xG se lit comme une analyse prudente : si `n < 300`, le signal reste echantillon faible ; si le ROI test est negatif, le signal est invalide ; si le Brier/log loss ne battent pas le marche no-vig, le xG n'ameliore pas la probabilite.

## Understat Multi-Season Data Probe

La phase V6.9 prepare la prochaine piste xG : Understat multi-saisons via `soccerdata`. Understat couvre plusieurs grandes ligues et peut donner plus de volume que le dataset EPL 2024-2025 seul.

`soccerdata` est optionnel. S'il est absent :

```bash
python -m pip install soccerdata
```

Verifier l'environnement :

```bash
python understat_probe.py --check
```

Commande reelle a lancer manuellement, hors tests :

```bash
python understat_probe.py --league EPL --seasons 2020,2021,2022,2023,2024 --output external_data/understat_probe/epl_2020_2024_matches.csv
python understat_probe.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
```

Le CSV exporte vise ces colonnes : date, league, season, home/away team, goals, home/away xG, result, source et source_match_id. Il est compatible avec :

```bash
python external_xg_lab.py --profile external_data/understat_probe/epl_2020_2024_matches.csv
python external_xg_features.py --external external_data/understat_probe/epl_2020_2024_matches.csv --xgabora data/features_modern.csv --output reports/understat_xg_rolling_features.csv
python xg_model_lab.py --features reports/understat_xg_rolling_features.csv
```

xgabora reste la base betting principale parce qu'elle contient les cotes et le volume historique. Understat sert seulement d'enrichissement xG laboratoire. Aucun signal Understat ne doit etre active sans rolling pre-match, benchmark gouvernance et validation humaine.

## V7.2 Understat xG Full Pipeline Quality Gate

V7.2 ajoute un controle qualite complet autour de l'export Understat EPL 2020-2025. L'ancien export de 1520 lignes etait incomplet : `soccerdata` interpretait la saison courte `2021` de facon ambigue, ce qui pouvait pointer vers `20-21` au lieu de produire `2021-2022`. Le nouvel export utilise des saisons explicites `2020-2021`, `2021-2022`, `2022-2023`, `2023-2024`, `2024-2025` et atteint 1900 lignes attendues pour cinq saisons EPL.

Le xG final reste une statistique post-match. V7.2 ne l'utilise jamais directement pour predire le meme match : il doit d'abord passer par des rolling features anti-fuite calculees uniquement avec les matchs precedents. Un Brier legerement meilleur ne suffit pas. Si le ROI test est negatif, l'edge est invalide. Si la CLV est absente, toute promotion reste bloquee. Telegram et Railway restent en attente.

Commandes locales V7.2 :

```bash
python understat_probe.py --league EPL --seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output external_data/understat_probe/epl_2020_2025_matches.csv
python understat_probe.py --profile external_data/understat_probe/epl_2020_2025_matches.csv
python xg_dataset_quality.py --external external_data/understat_probe/epl_2020_2025_matches.csv --league EPL --expected-seasons 2020-2021,2021-2022,2022-2023,2023-2024,2024-2025 --output reports/understat_epl_2020_2025_quality.json --html reports/understat_epl_2020_2025_quality.html
python understat_xg_pipeline.py --external external_data/understat_probe/epl_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix understat_epl_2020_2025
python xg_model_lab.py --features reports/understat_epl_2020_2025_rolling_features.csv --output reports/understat_epl_2020_2025_xg_model.json --html reports/understat_epl_2020_2025_xg_model.html
python benchmark_governance.py --features data/features_modern.csv --xg-lab reports/understat_epl_2020_2025_rolling_features.csv --xg-quality reports/understat_epl_2020_2025_quality.json --xg-model reports/understat_epl_2020_2025_xg_model.json --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
python report_runner.py --xg-understat
```

Tous les rapports V7.2 restent dans `reports/`. Les donnees Understat restent dans `external_data/`. Rien ne modifie `oracle_db.json`, `data/MATCHES.csv` ou `data/features_modern.csv`.

## V7.3 Multi-League Join Diagnostics

V7.3 ajoute une couche de diagnostic de jointure Understat/xgabora pour les ligues qui exportent bien mais joignent mal. Le cas La Liga illustre le probleme : le CSV Understat peut etre complet, avec 1900 matchs et 100% de xG, mais une jointure a environ 39.89% rend le modele inutilisable serieusement. Une mauvaise jointure peut venir des accents, alias, abreviations, competitions differentes, dates decalees, equipes promues/releguees ou calendriers manquants.

EPL est fiable a 98% dans l'etat actuel, mais La Liga doit etre corrigee avant modeling. Les alias sont proposes, jamais appliques aveuglement aux CSV source. Les fichiers `data/features_modern.csv` et `external_data/` restent inchanges.

Commandes :

```bash
python join_diagnostics.py --xgabora data/features_modern.csv --external external_data/understat_probe/laliga_2020_2025_matches.csv --output reports/laliga_join_diagnostics.json --html reports/laliga_join_diagnostics.html
python external_xg_lab.py --evaluate-join --xgabora data/features_modern.csv --external external_data/understat_probe/laliga_2020_2025_matches.csv
python understat_xg_pipeline.py --external external_data/understat_probe/laliga_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix laliga_2020_2025 --skip-benchmark --strict-join
```

Lecture du diagnostic :

- `join_rate_before_alias` mesure la jointure stricte avant alias ;
- `join_rate_after_alias` mesure la jointure stricte apres alias manuel controle ;
- `join_rate_fuzzy` reste une piste de diagnostic, pas une jointure automatique ;
- `join_quality=insuffisant` bloque le modele et toute promotion ;
- les suggestions d'alias doivent etre revues humainement avant d'ajouter un mapping.

Seuils V7.3 :

- 90% et plus : excellent ;
- 75-90% : exploitable prudent ;
- 50-75% : fragile ;
- moins de 50% : insuffisant pour modele serieux.

On ne lance pas encore toutes les ligues parce que chaque ligue doit d'abord passer son quality gate dataset, puis son quality gate jointure. Sans CLV positive et gouvernance complete, meme une jointure excellente ne cree pas d'edge jouable.

## V7.4 Bundesliga Team Alias Expansion

V7.4 etend les alias Bundesliga. Le premier diagnostic Bundesliga etait sainement bloque par `--strict-join` : l'export Understat etait complet, avec 1530 matchs, cinq saisons de 306 matchs et 100% de xG, mais la jointure restait autour de 24.12%. Un dataset xG propre ne suffit pas si les noms d'equipes ne rejoignent pas xgabora.

La Bundesliga utilise souvent des noms raccourcis dans xgabora : `Leverkusen`, `Ein Frankfurt`, `MGladbach`, `Dortmund`, `FC Koln`, `Mainz`, `RB Leipzig`, `Werder Bremen`, `Union Berlin`, `Hertha`, `Schalke 04`. V7.4 mappe explicitement les variantes Understat comme `Bayer Leverkusen`, `Eintracht Frankfurt`, `Borussia Monchengladbach`, `FC Bayern München`, `1. FC Union Berlin`, `VfL Wolfsburg`, `VfB Stuttgart`, `Mainz 05` ou `Greuther Fürth`.

Relancer le diagnostic :

```bash
python join_diagnostics.py --xgabora data/features_modern.csv --external external_data/understat_probe/bundesliga_2020_2025_matches.csv --output reports/bundesliga_join_diagnostics.json --html reports/bundesliga_join_diagnostics.html --league Bundesliga
python understat_xg_pipeline.py --external external_data/understat_probe/bundesliga_2020_2025_matches.csv --xgabora data/features_modern.csv --out-prefix bundesliga_2020_2025 --skip-benchmark --strict-join
```

Le blocage strict est une protection, pas un echec : si la jointure reste sous 75%, le modele doit attendre. Meme au-dessus de 90%, la promotion reste impossible sans CLV positive, sample suffisant, bootstrap favorable et gouvernance complete.

## V7.5 Big Five xG Completion & CLV Readiness

V7.5 prepare la couverture Big Five sans lancer de recuperation reseau. EPL, La Liga et Bundesliga sont maintenant des laboratoires exploitables ou en cours de controle, et les alias ont montre qu'une jointure faible peut devenir excellente quand les noms Understat/xgabora sont audites. Serie A et Ligue 1 disposent d'alias prudents pour les exports futurs.

La phase ajoute `multi_league_xg_aggregator.py` pour comparer les rapports xG par ligue, et `clv_readiness_report.py` pour expliquer pourquoi la CLV est ou non calculable. Si la CLV reste absente, tout ROI positif a faible sample reste observation/watchlist maximum. Un Brier ou log loss legerement meilleur ne suffit pas a creer un edge betting.

Commandes locales :

```bash
python multi_league_xg_aggregator.py --reports-dir reports --output reports/big5_xg_summary.json --html reports/big5_xg_summary.html
python clv_readiness_report.py --features data/features_modern.csv --output reports/clv_readiness.json --html reports/clv_readiness.html
python report_runner.py --big5-xg --skip-benchmark
```

Telegram et Railway restent en attente. Avant toute aide decisionnelle, il faut des closing odds fiables, une CLV positive, un ROI test recent positif, un sample suffisant, bootstrap favorable, calibration correcte, correction multiple testing et gouvernance complete.

## V7.6 Big Five Completion & Closing Odds Recovery

V7.6 finalise les derniers alias utiles avant completion Big Five et ajoute le plan concret de recuperation des closing odds. Serie A conserve un export propre de 1900 matchs avec 100% xG ; le diagnostic a montre une jointure deja excellente mais encore penalisee par `Parma Calcio 1913`, maintenant mappe vers `Parma`. Bundesliga conserve les aliases longs/courts et ajoute les cas restants `St. Pauli` et `Holstein Kiel`. Ligue 1 est prete pour execution humaine, sans lancement reseau automatique.

La nouvelle couche closing odds est volontairement separee :

- `closing_odds_probe.py` lit seulement le header et un echantillon de `data/MATCHES.csv` pour savoir si des colonnes closing existent ;
- `features_closing_enricher.py` peut produire une preview dans `reports/features_with_closing_preview.csv`, jamais dans `data/` ;
- `clv_readiness_report.py` distingue maintenant CLV calculable maintenant et CLV calculable apres enrichissement ;
- `report_runner.py --closing-readiness` lance le probe, la readiness enrichie et la gouvernance locale.

Cette phase ne modifie ni `data/MATCHES.csv`, ni `data/features_modern.csv`, ni la DB. Meme si xG ameliore legerement Brier/log loss, cela reste une observation technique sans CLV fiable, sample suffisant et validation statistique complete.

## V7.7 Partial CLV Pipeline

V7.7 transforme la decouverte `C_LTH` / `C_LTA` en pipeline CLV partiel strict. Ces colonnes permettent seulement une CLV H2H home/away quand la ligne de feature correspond exactement au cote joue. Le draw, les totals et BTTS restent exclus tant que leurs colonnes closing exactes ne sont pas presentes.

Le flux local est :

- `closing_odds_probe.py` classe le scope en `none`, `partial` ou `complete` ;
- `features_closing_enricher.py` cree uniquement `reports/features_with_closing_preview.csv` ;
- `clv_analysis.py` lit `clv_available` et ignore les lignes non couvertes ;
- `clv_readiness_report.py --preview` mesure la couverture reelle ;
- `benchmark_governance.py` signale la CLV partielle comme diagnostic, jamais comme validation globale.

La CLV partielle peut aider a savoir si certains signaux H2H prenaient de meilleurs prix que la closing line. Elle ne valide pas un modele global, ne valide pas les draws/totals/BTTS et ne debloque aucune promotion si le sample est trop faible ou si la gouvernance complete echoue.

## V7.8 Closing Column Forensics

V7.8 ajoute une analyse forensique des colonnes closing. Une colonne nommee `C_*` ne suffit plus : `closing_odds_probe.py` profile les valeurs, calcule min/max/mediane/percentiles, compte les valeurs `0-1`, les valeurs plausibles `1.01-100`, les textes et les vides, puis donne un verdict par colonne.

Les verdicts possibles sont `decimal_odds_plausible`, `numeric_but_not_odds`, `mostly_empty`, `text_or_code` et `unknown`. `features_closing_enricher.py` refuse maintenant toute colonne detectee par nom mais non validee par les valeurs. `clv_readiness_report.py` expose le bloqueur exact : colonnes closing detectees par nom mais valeurs non plausibles.

Cette phase ne calcule pas de CLV si les valeurs ne sont pas des cotes decimales. Elle confirme que le projet reste laboratoire prudent tant qu'une source closing fiable n'est pas identifiee.

## V8.0 Shadow Mode & Manual CLV Capture

V8.0 cree un mode shadow local pour les matchs futurs. Le bot peut enregistrer une observation Oracle dans `reports/shadow_ledger.csv`, avec la cote prise, le marche, le cote joue, la strategie, la raison et le statut. Ce ledger ne conseille aucune mise : il sert uniquement a construire une preuve live propre.

La CLV shadow n'est calculee que si une vraie cote closing decimale est fournie manuellement via `closing_manual_import.py`. Si la closing odds manque, la CLV reste non calculable. `shadow_clv_report.py` resume ensuite coverage CLV, CLV moyenne, CLV positive rate, ROI si resultats connus, sample size et verdict shadow.

Regles V8.0 :

- pas de Telegram agressif ;
- pas de Railway ;
- pas de pick automatique ;
- pas de Kelly reel ;
- sample < 1000 = promotion impossible ;
- CLV positive en shadow = observation, pas garantie de rentabilite ;
- sans closing fiable, le mode shadow reste un journal d'analyse.

## Statistical Proof Foundation

La phase V7.0 ajoute la couche de preuve statistique. Elle ne cree aucun pick, ne modifie pas Telegram, ne modifie pas Railway et ne touche pas a `oracle_db.json`.

Commandes principales :

```bash
python clv_analysis.py --features data/features_modern.csv --output reports/clv_report.json --html reports/clv_report.html
python calibration_report.py --features data/features_modern.csv --prob-column no_vig_probability --output reports/calibration_report.json --html reports/calibration_report.html
python statistical_validation.py --features data/features_modern.csv --output reports/statistical_validation.json --html reports/statistical_validation.html
python report_runner.py --statistical
```

Pourquoi ROI court terme ne suffit pas :

- le football pre-match est un marche efficient ;
- 300 ou 1000 picks peuvent encore etre compatibles avec du bruit ;
- un ROI positif choisi apres coup peut venir du data snooping ;
- validation positive mais test negatif invalide le signal.

Pourquoi CLV est prioritaire :

- avoir pris 2.10 quand la closing line finit a 2.00 est une information forte ;
- avoir pris 1.90 quand la closing line finit a 2.00 est une alerte ;
- sans CLV positive, aucun signal ne peut devenir candidat robuste ;
- certaines closing odds Pinnacle recentes peuvent demander controle de source, surtout apres 2025-07-23.

Pourquoi multiple testing est dangereux :

- tester des dizaines de segments finit presque toujours par produire un faux positif ;
- la correction Benjamini-Hochberg penalise les p-values quand plusieurs strategies sont comparees ;
- un signal qui passe avant correction mais echoue apres correction reste fragile.

Comment lire bootstrap / Monte Carlo :

- le bootstrap donne des percentiles de ROI plausibles sous re-echantillonnage ;
- si le percentile 5% du ROI est inferieur ou egal a 0, le signal reste observation ;
- Monte Carlo sert a sentir la dispersion, pas a creer une promesse de profit ;
- le drawdown simule rappelle qu'un edge faible peut rester difficile a supporter.

Comment lire les reliability curves :

- Brier et log loss mesurent la qualite probabiliste ;
- ECE mesure l'erreur moyenne de calibration ;
- MCE mesure le pire ecart de calibration observe ;
- une probabilite mal calibree ne doit pas piloter une decision.

Pourquoi Kelly ne cree pas d'edge :

- Kelly gere une fraction de mise si l'edge existe deja ;
- il ne transforme pas un modele fragile en strategie profitable ;
- dans Oracle Football Bot, Kelly reste reserve a la simulation.

Pourquoi Telegram et Railway doivent attendre :

- aucun signal robuste n'est active ;
- `production_allowed` signifie seulement aide a la decision explicable, jamais pari automatique ;
- Railway attend une preuve statistique robuste, CLV positive et revue humaine.

## Scientific Benchmark

La phase V6.7 consolide les resultats disponibles dans un benchmark scientifique local. Elle compare le marche, les regles Oracle, les segments, les modeles ML et le futur lab xG avec une meme logique de prudence.

```bash
python benchmark_governance.py --features data/features_modern.csv --summary-json reports/benchmark_summary.json --html reports/benchmark_governance.html
```

Si une section echoue, le benchmark continue et marque la section comme indisponible. Le rapport reste descriptif : il ne modifie pas la DB, ne lance pas Telegram et ne cree aucun pick. Si CLV, calibration ou validation statistique sont absentes, les candidats robustes sont bloques.

## Model Governance

Chaque strategie recoit un `robustness_score` prudent sur 100. Le statut peut etre :

- candidat robuste, mais pas pick automatique ;
- observation forte a confirmer ;
- fragile / surveillance ;
- faible / non confirme ;
- invalide ou a eviter ;
- invalide fuite de donnees.

Regles importantes :

- ROI test 2024+ negatif ou nul : jamais robuste.
- CLV absente ou negative : jamais candidat robuste.
- Bootstrap ROI 5e percentile inferieur ou egal a 0 : jamais candidat robuste.
- Correction multiple testing echouee : jamais candidat robuste.
- Validation positive mais test negatif : invalide.
- Test absent : maximum fragile.
- Sample test inferieur a 300 : echantillon faible.
- Sample test inferieur a 1000 : observation maximum.
- Fuite post-match : score force a 0.

## Model Registry

`model_registry.json` contient uniquement des metadonnees et resultats agreges :

- nom, type, version ;
- periodes train/validation/test ;
- features utilisees ;
- risque de fuite ;
- metriques validation/test ;
- score robustesse ;
- statut, decision et notes.

Il ne contient pas de secrets, pas de dataset lourd et pas de predictions individuelles.

## Promotion Policy

La politique de promotion est documentee dans `docs/model_promotion_policy.md`. Meme le niveau `production_allowed` ne signifie pas pari automatique : cela autorise seulement un affichage explicable comme aide a la decision.

## Decision Policy

`decision_policy.py` formalise les regles de prudence dans des fonctions testables :

- `classify_strategy`
- `can_promote_to_watchlist`
- `can_promote_to_candidate`
- `can_use_in_shadow`
- `can_use_in_telegram`

La calibration compte davantage que l'accuracy brute. Le test 2024+ reste la verite finale. Les signaux peuvent rester longtemps en watchlist sans etre actives.

## Telegram

Telegram reste la couche historique du bot, mais les phases V6.x locales ne doivent pas le rendre plus agressif. Les rapports locaux, le ML, le pricing et le lab externe ne doivent pas envoyer de message Telegram.

Le point d'entree Telegram/Railway reste :

```bash
python main.py
```

Ne pas l'utiliser pour valider les phases d'audit local.

## Railway plus tard

Ne pas redeployer Railway maintenant. Un redeploiement n'a de sens qu'apres :

- strategie robuste positive sur validation puis test 2024+ ;
- volume suffisant ;
- drawdown acceptable ;
- absence de fuite de donnees ;
- revue explicite des changements Telegram.

## Securite

Fichiers a ne pas versionner :

- `oracle_db.json`
- `oracle_db_backup_*.json`
- `oracle_db_archive_*.json`
- `data/`
- `external_data/`
- `.env`
- `variable/`
- `reports/`

Verifier :

```bash
python project_audit.py
git ls-files -- oracle_db.json "oracle_db_backup_*.json" "oracle_db_archive_*.json" data external_data .env variable reports
```

## Commandes principales

La liste complete est dans `COMMANDS.md`.

```bash
python -m compileall -q .
python test_project_audit.py
python test_pricing.py
python test_feature_builder.py
python test_model_trainer.py
python test_backtest_evaluator.py
python test_report_runner.py
python project_audit.py
```

## Etat actuel : aucune strategie robuste positive

Etat V8.1 Shadow UX, Daily Workflow, Evidence Dashboard & Safety Hardening :

- memoire moderne 2015-2025 ;
- environ 528066 records regles ;
- pricing et no-vig disponibles ;
- rolling pre-match disponibles ;
- post-match features exclues par defaut ;
- External Dataset Lab disponible ;
- External xG Integration Lab disponible ;
- External xG Rolling Features Lab disponible ;
- Understat Multi-Season Data Probe disponible ;
- Understat xG Full Pipeline Quality Gate disponible ;
- diagnostics multi-ligues et aliases Big Five disponibles ;
- agregateur Big 5 xG disponible ;
- CLV readiness disponible ;
- closing odds probe disponible ;
- preview features closing disponible uniquement dans `reports/` ;
- CLV partielle H2H home/away disponible en diagnostic si `C_LTH/C_LTA` sont presents ;
- V7.8 a rejete `C_LTH/C_LTA` comme `numeric_but_not_odds` dans `data/MATCHES.csv` local ;
- shadow ledger disponible pour collecter les observations live de juin ;
- workflow quotidien shadow disponible via `shadow_workflow.py` ;
- templates CSV disponibles via `shadow_templates.py` ;
- import manuel des resultats disponible via `results_manual_import.py` ;
- import manuel de closing odds disponible par `shadow_id` ;
- rapport CLV shadow enrichi avec ROI unite, drawdown, splits et blockers, observation seulement ;
- dashboard shadow evidence disponible ;
- V8.2 Operations Center disponible via `oracle_ops.py` ;
- evidence gate disponible via `evidence_gate.py` ;
- audit qualite ledger disponible via `shadow_quality_audit.py` ;
- simulateur shadow synthetique disponible via `shadow_simulator.py` ;
- sample size planner disponible via `sample_size_planner.py` ;
- formatter texte shadow disponible sans envoi via `shadow_message_formatter.py` ;
- draw, totals et BTTS restent exclus sans colonnes closing exactes ;
- CLV, calibration et validation statistique disponibles ;
- Scientific Benchmark et Model Governance disponibles ;
- rapport central local disponible ;
- aucun signal robuste active ;
- ML actuel ne bat pas le marche no-vig sur test 2024+ ;
- favoris H2H proches du break-even mais non confirmes.

## Roadmap

Priorite suivante :

1. Commit/push les phases locales prudentes.
2. Initialiser `shadow_ledger.py --init`.
3. Ajouter les observations shadow des matchs de juin sans recommandation de mise.
4. Lancer manuellement Ligue 1 Understat, sans automatiser de reseau.
5. Importer les closing odds manuelles fiables avec `closing_manual_import.py`.
6. Relancer `shadow_clv_report.py` et lire sample/coverage/CLV moyenne.
7. Chercher une source closing complete et fiable si le manuel ne suffit pas.
8. Ne penser a Railway ou Telegram qu'apres CLV positive, preuve statistique robuste et revue humaine.

## V8.1 Shadow UX, Daily Workflow & Evidence Dashboard

V8.1 transforme le shadow mode en routine quotidienne locale :

- `shadow_workflow.py --init` initialise le ledger et les templates CSV ;
- `shadow_ledger.py --add-csv` importe plusieurs observations manuelles ;
- `shadow_templates.py` genere les templates candidats, closing et resultats ;
- `closing_manual_import.py` ajoute uniquement des closing odds reelles ;
- `results_manual_import.py` ajoute les resultats manuels ;
- `shadow_clv_report.py` calcule CLV, ROI unite, profit, drawdown et splits ;
- `report_runner.py --daily-shadow` regenere les preuves et le dashboard.

Ce workflow reste un journal de preuve. Il n'utilise pas Kelly, ne cree aucune mise, ne publie rien sur Telegram et ne transforme jamais une observation shadow en recommandation active. Sans CLV manuelle fiable et sans sample largement suffisant, le verdict reste `not_validated` ou `observation_only`.

## V8.2 Operations Center, Evidence Gate & June Runbook

V8.2 ajoute une couche operations pour utiliser Oracle Bot au quotidien en juin :

- `oracle_ops.py --health` verifie les modules, les dossiers ignores et les fichiers locaux attendus ;
- `oracle_ops.py --daily` affiche la checklist du jour ;
- `shadow_quality_audit.py` controle le ledger avant interpretation ;
- `evidence_gate.py` centralise les bloqueurs de preuve ;
- `shadow_simulator.py` genere des ledgers synthetiques pour tester le workflow ;
- `sample_size_planner.py` rappelle pourquoi 100, 300 ou 500 observations ne suffisent pas ;
- `shadow_message_formatter.py` prepare une preview texte privee, sans envoi Telegram.

Le statut maximum reste `ready_for_deep_review`, c'est-a-dire analyse approfondie requise. Il n'y a aucune mise reelle, aucune activation automatique, aucune promesse de rentabilite.

## V8.3 Odds Source Lab, Odds Snapshot & Shadow Automation

V8.3 ajoute un laboratoire de collecte de cotes sans reseau automatique :

- `odds_source_config.py` centralise les sources sans committer de secrets ;
- `odds_normalizer.py` convertit CSV/API vers un format snapshot standard ;
- `odds_snapshot_store.py` stocke les snapshots dans `reports/` ;
- `manual_odds_import.py` importe le CSV manuel ;
- `api_football_odds_adapter.py` et `the_odds_api_adapter.py` restent optionnels et refusent le reseau sans `--allow-network` ;
- `odds_to_shadow.py` transforme des snapshots valides en observations shadow ;
- `odds_closing_matcher.py` utilise uniquement des snapshots `is_near_close=true` pour renseigner une closing observee ;
- `odds_source_quality_report.py` mesure couverture, invalides, near-close et capacite CLV.

Cette phase ne valide aucun signal. Elle prepare la collecte de preuves : taken odds, near-close odds, coverage par marche, puis CLV seulement si la cote closing exacte existe.

Commandes principales :

```bash
python odds_source_config.py --write-example
python odds_source_config.py --check
python manual_odds_import.py --template reports/manual_odds_snapshot_template.csv
python manual_odds_import.py --input reports/manual_odds_snapshot.csv --store reports/odds_snapshots.csv
python odds_source_quality_report.py --snapshots reports/odds_snapshots.csv --output reports/odds_source_quality.json --html reports/odds_source_quality.html
python odds_to_shadow.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --dry-run
python odds_closing_matcher.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --dry-run
python oracle_ops.py --odds-lab
python report_runner.py --odds-lab --skip-dashboard
```

`C_LTH/C_LTA` dans `data/MATCHES.csv` restent rejetes comme cotes decimales non plausibles. V8.3 ne les transforme pas en CLV et ne fabrique aucune closing odds.
