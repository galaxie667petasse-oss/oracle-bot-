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
