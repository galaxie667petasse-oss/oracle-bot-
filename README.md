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

## Tests simples

```bash
python test_settlement.py
python test_shadow_learning.py
python test_agent_weights.py
python test_calibration.py
python test_xgabora_dataset_import.py
```
