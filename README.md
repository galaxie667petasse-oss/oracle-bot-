# Oracle Bot

Bot Telegram de scan football avec calibration progressive, mémoire locale et mémoire PostgreSQL Railway quand `DATABASE_URL` existe.

## Démarrage Railway

Le point d'entrée reste volontairement fixe :

```bash
python main.py
```

`main.py` lance `bot_app_v52.py`, qui enveloppe le moteur Telegram historique dans `bot_app.py`.

## Mémoire

- Sans `DATABASE_URL`, le bot utilise `oracle_db.json`.
- Avec `DATABASE_URL`, `store.py` lit PostgreSQL en priorité via `persistent_memory.py`.
- `save_db()` conserve aussi une copie locale comme secours.

## Backtest CSV

Le backtest permet d'entraîner la mémoire sans attendre les prochains matchs et sans appeler Telegram ni API externe.

Format requis :

```csv
date,home,away,competition,market_type,pari,odds,result
```

Commande :

```bash
python backtest_import.py docs/backtest_example.csv
```

Par défaut, les lignes sont ajoutées comme candidats fantômes historiques. Une colonne optionnelle `visible` peut valoir `oui`, `true`, `1`, `visible` ou `pick` pour les importer comme picks visibles.

## Import xgabora et calibration

Le dataset `xgabora/Club-Football-Match-Data-2000-2025` peut être importé avec :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --limit 1000
```

Les premières statistiques xgabora montrent souvent un ROI négatif sur beaucoup de catégories, surtout les marchés `h2h`, `draw` et les cotes hautes. C'est normal sur un historique brut : le but n'est pas de parier plus, mais de refuser davantage les catégories faibles.

La calibration Oracle utilise cet historique pour durcir automatiquement :

- EV minimum pour un top pick ;
- score conseil minimum ;
- danger maximum ;
- limites sur les cotes H2H/draw ;
- pénalités sur marchés ou tranches de cotes avec ROI négatif.

Une tranche `low` peut afficher un ROI positif, mais elle reste peu rentable et sensible aux frais, limites et variations de cote. Le bot ne doit donc jamais transformer ce signal en excès de confiance.

Import progressif conseillé :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --limit 1000
python xgabora_dataset_import.py data/MATCHES.csv --limit 10000
python xgabora_dataset_import.py data/MATCHES.csv
```

Après chaque étape, vérifier `/stats`, `/memoire` et `/diagnostic`. L'importeur ignore les candidats déjà présents avec une clé stable `date + home + away + market_type + pari + odds`, donc il ne faut pas réimporter volontairement les mêmes lignes pour chercher à gonfler l'échantillon.

## Analyse de segments

Après un import large, le ROI global peut rester négatif sans rendre le projet inutile. Il indique surtout que les marchés bruts sont difficiles et que le bot doit refuser beaucoup.

La commande Telegram `/segments` cherche des sous-groupes plus précis :

- marché seul ;
- tranche de cote seule ;
- marché + tranche de cote ;
- marché + ligue ;
- marché + tranche + ligue ;
- domicile/extérieur en H2H ;
- favori/outsider ;
- profils Elo si disponibles ;
- période récente ou ancienne.

Un segment n'est utilisé pour ajuster une décision que s'il a assez de volume. Sous 100 résultats, il est ignoré pour la décision. Entre 100 et 300, il reste un signal faible. À partir de 300, il devient exploitable, mais seulement comme garde-fou statistique.

Un segment positif donne au maximum un petit bonus prudent. Il ne peut jamais compenser une EV négative, un danger trop haut, une très haute cote bloquée ou un marché draw globalement mauvais sans vrai segment draw positif. Le but reste de refuser mieux, pas de forcer plus de paris.

## Backtest train/test

Le ROI global historique ne suffit pas : il peut seulement décrire le passé. Pour vérifier si une règle généralise, il faut apprendre sur une période train puis mesurer sur une période test jamais utilisée pour construire la calibration.

Commande par défaut :

```bash
python backtest_evaluator.py
```

Découpage personnalisé :

```bash
python backtest_evaluator.py --train-to 2022-12-31 --test-from 2023-01-01 --json out/backtest.json
```

L'outil compare plusieurs stratégies : baseline brute, exclusion des segments bloqués, marchés total seulement, total low/mid, Oracle strict, favoris seulement et exclusion des outsiders. Il affiche le ROI, le profit unité, le drawdown et le détail par marché/tranche de cote.

Un bot sérieux doit souvent refuser : si aucune stratégie n'est positive sur le test, le bon signal est de rester plus strict. Même un ROI positif faible sur le test n'est pas une preuve définitive.

## Feature matrix et ML leger

La phase V6.1 ajoute une analyse locale hors production. Elle ne modifie pas la memoire, ne lance pas Telegram, n'appelle aucune API et ne transforme jamais un modele en generateur automatique de picks.

La matrice de features se construit avec :

```bash
python feature_builder.py --output data/features_modern.csv
```

Elle exporte les records regles visibles et fantomes en CSV avec les cotes, probabilites implicites, probabilites no-vig, marge marche, variables Elo, formes recentes, type de marche et drapeaux simples comme favori, outsider, home/away, over/under. Si un champ pricing manque dans la memoire, il est recalcule quand le marche complet du match le permet. Les champs indisponibles restent vides : l'outil ne cree pas de cote artificielle.

Le modele local se lance ensuite avec :

```bash
python model_trainer.py --features data/features_modern.csv
python model_trainer.py --features data/features_modern.csv --market h2h
python model_trainer.py --features data/features_modern.csv --market total
```

Le split temporel est fixe : train 2015-2022, validation 2023, test final 2024+. La validation sert a choisir un seuil d'edge, puis le test 2024+ sert uniquement a verifier. Le test ne doit jamais servir a choisir la regle.

Le rapport compare la probabilite du modele a la baseline marche `no_vig_probability` avec :

- `Brier score` : plus bas est meilleur ; il mesure l'erreur quadratique de probabilite.
- `log loss` : plus bas est meilleur ; il penalise fortement les predictions trop confiantes et fausses.
- buckets de calibration : comparent la probabilite moyenne predite au vrai taux de victoire.
- simulations d'edge : `model_probability - no_vig_probability` avec plusieurs seuils, sans pick automatique.

Un bucket bien calibre a un taux reel proche de la probabilite predite. Si le modele predit 0.60 mais gagne seulement 0.52, il est surconfiant. S'il predit 0.52 mais gagne 0.60, il est sous-confiant. Meme un modele prometteur reste non jouable tant que validation et test 2024+ ne confirment pas un signal robuste avec assez de volume.

Le test 2024+ reste la verite finale parce qu'il represente les matchs les plus recents et n'est pas utilise pour entrainer, calibrer ou choisir les seuils. Si la validation est positive mais que 2024+ devient negatif, le signal est invalide.

## Enrichissement local et anti-fuite

La phase V6.2 enrichit la matrice avec des informations terrain issues du CSV local `MATCHES.csv`/`Matches.csv`, sans API ni scraping. Les stats finales du match comme tirs, tirs cadres, corners, cartons, score mi-temps et clean sheets sont des `post-match features` : elles decrivent ce qui s'est passe pendant le match.

Ces colonnes ne doivent pas predire ce meme match en mode live, car le bot ne les connait pas avant le coup d'envoi. `model_trainer.py` les exclut donc par defaut et affiche la liste des features retirees pour eviter la fuite de donnees.

Pour une analyse volontairement non predictive, on peut les inclure explicitement :

```bash
python model_trainer.py --features data/features_modern.csv --allow-post-match-features
```

Cette option sert uniquement a verifier la valeur descriptive des stats finales. Elle ne doit pas etre utilisee pour juger un modele exploitable avant match.

Pour donner du contexte terrain sans fuite, `feature_builder.py` calcule aussi des rolling features pre-match par equipe, par exemple buts marques/encaisses avg5, tirs avg5, corners avg5, BTTS rate5 et over 2.5 rate5. Pour un match donne, ces moyennes utilisent seulement les matchs precedents de l'equipe, jamais le match courant ni un match futur. Les matchs d'une meme date sont traites ensemble avant mise a jour de l'historique afin d'eviter une fuite entre deux matchs du meme jour.

Le rapport ML compare maintenant :

- baseline sans rolling ;
- modele avec rolling pre-match ;
- marche no-vig.

Une amelioration de Brier score ou log loss doit rester coherente sur validation puis test 2024+. Si les edges positifs validation deviennent negatifs sur test, le signal est invalide, meme si une feature semble intuitive.

## External Dataset Lab

La phase V6.3 ajoute un laboratoire de datasets externes. Il ne remplace pas xgabora, ne telecharge rien, ne scrape rien, ne modifie pas `oracle_db.json` et ne branche aucune source aux picks. xgabora reste la base principale parce qu'il fournit le volume historique, les resultats et les cotes necessaires pour mesurer le marche.

Le modele actuel ne bat pas encore le marche no-vig sur test 2024+. Les rolling features pre-match donnent du contexte, mais les signaux positifs validation sont invalides sur 2024+. Le prochain axe raisonnable est donc de profiler des sources plus riches en xG, tirs, lineups et stats joueurs/equipes, sans les croire avant test.

Commandes utiles :

```bash
python external_dataset_probe.py --list
python external_dataset_probe.py --profile-csv chemin/vers/fichier.csv
python external_dataset_probe.py --profile-folder chemin/vers/dossier
python external_dataset_probe.py --recommend chemin/vers/fichier.csv
python external_join_plan.py --xgabora data/features_modern.csv --external chemin/vers/fichier.csv
python external_adapters/epl_fbref_lab.py --profile chemin/vers/dossier
```

Le score d'utilite Oracle note `match_results`, `odds`, `xg`, `shots`, `lineups`, `player_stats`, `team_stats`, `recency`, `join_possible_with_xgabora` et `leak_risk`. Un dataset sans cotes mais riche en xG/stats avancees peut enrichir ou servir de laboratoire, mais il ne remplace pas xgabora.

Pour eviter les fuites, les rapports marquent les colonnes post-match comme xG final, tirs finaux, corners finaux, scores et resultats. Ces colonnes ne doivent pas predire le meme match si elles ne sont connues qu'apres coup. Aucune source externe ne doit influencer les picks sans jointure controlee et backtest train/validation/test.

## Politique de récence des données

Les données 2000-2011 sont utiles comme archive, mais elles ne doivent pas dominer les décisions actuelles. Le football, les marchés de cotes, les modèles bookmaker et les compétitions ont trop changé pour traiter 2002 comme 2024.

Oracle sépare donc la mémoire en périodes :

- `archive_pre2012` : poids 0.15 ;
- `transition_2012_2014` : poids 0.35 ;
- `modern_2015_2019` : poids 0.70 ;
- `recent_2020_2023` : poids 1.00 ;
- `test_2024_plus` : poids 1.00, à garder surtout comme test final.

La calibration privilégie 2015+ et surtout 2020+. Un signal positif uniquement présent dans l'archive ancienne est dangereux : il peut refléter un vieux contexte de marché et ne doit jamais suffire à débloquer un top pick moderne.

Commandes conseillées :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --inspect-dates
python xgabora_dataset_import.py data/MATCHES.csv --from 2015-01-01 --to 2023-12-31
python xgabora_dataset_import.py data/MATCHES.csv --from 2020-01-01 --to 2023-12-31
python backtest_evaluator.py --preset modern
```

## Tests simples

```bash
python test_settlement.py
python test_shadow_learning.py
python test_agent_weights.py
python test_calibration.py
python test_segment_analysis.py
python test_backtest_evaluator.py
python test_segments_text.py
python test_xgabora_dataset_import.py
```
