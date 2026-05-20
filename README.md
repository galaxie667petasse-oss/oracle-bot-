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
