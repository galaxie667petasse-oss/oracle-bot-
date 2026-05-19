# Import xgabora Club-Football-Match-Data-2000-2025

Ce script importe le fichier `MATCHES.csv` du dataset gratuit `xgabora/Club-Football-Match-Data-2000-2025` dans la mémoire Oracle Bot.

Source dataset :

- GitHub : `xgabora/Club-Football-Match-Data-2000-2025`
- Hugging Face : `xgabora/Club-Football-Match-Data-2000-2025`

Le dataset contient des résultats, statistiques, cotes pré-match et informations Elo/Form. L'importeur n'appelle aucune API externe et n'utilise que les cotes présentes dans le CSV.

## Commande de base

```bash
python xgabora_dataset_import.py data/MATCHES.csv
```

Les lignes sont importées comme candidats fantômes historiques dans `db["scans"][date]["candidates"]`, puis :

- `build_learning(db)` est recalculé ;
- `agent_weights(db)` est recalculé ;
- `save_db(db)` sauvegarde dans PostgreSQL si `DATABASE_URL` existe, sinon dans la mémoire locale.

## Options

Limiter le nombre de matchs lus :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --limit 1000
```

Filtrer par période :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --from 2024-01-01 --to 2025-12-31
```

Filtrer par divisions :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --competitions E0,SP1,I1,D1,F1
```

Tester sans sauvegarder :

```bash
python xgabora_dataset_import.py data/MATCHES.csv --dry-run
```

## Cotes utilisées

Le script n'invente jamais de cote. Un marché est ignoré si sa cote est absente ou non numérique.

Ordre de préférence :

- `MaxHome`, puis `OddHome` pour la victoire domicile ;
- `MaxDraw`, puis `OddDraw` pour le nul ;
- `MaxAway`, puis `OddAway` pour la victoire extérieur ;
- `MaxOver25`, puis `Over25` pour over 2.5 ;
- `MaxUnder25`, puis `Under25` pour under 2.5.

## Marchés générés

Pour chaque match avec score final et cotes disponibles :

- `h2h` domicile ;
- `draw` ;
- `h2h` extérieur ;
- `total` over 2.5 ;
- `total` under 2.5.

Tous les candidats sont invisibles :

```python
shadow = True
visible = False
```

## Champs Elo et forme

Si les colonnes existent, elles sont conservées :

- `home_elo`
- `away_elo`
- `elo_diff`
- `form3_home`
- `form3_away`
- `form5_home`
- `form5_away`

Ces champs servent de matière de calibration. Les votes agents ajoutés par l'importeur sont des votes heuristiques prudents basés sur la cote, le marché et l'écart Elo disponible.

## Sécurité

- Ne modifie pas `main.py`.
- Ne modifie pas le `Dockerfile`.
- Ne touche pas aux clés API.
- N'appelle pas Telegram.
- N'appelle aucune API externe.
