# Générateur de dataset historique

Ce générateur construit `data/historical_backtest.csv` pour entraîner Oracle Bot avec des matchs déjà terminés.

## Pourquoi les vraies cotes historiques sont obligatoires

Oracle Bot calibre ses agents sur la relation entre un marché, une cote, une value estimée et le résultat final. Une cote inventée fausse cette relation et peut entraîner les agents dans une mauvaise direction.

Le script n'invente donc jamais de cotes. Si un fournisseur ne renvoie pas de cote historique exploitable, la ligne est ignorée.

## Pourquoi les résultats seuls ne suffisent pas

Un résultat final dit seulement ce qui s'est passé. Pour apprendre si un pari était intéressant, il faut aussi savoir à quelle cote le marché était proposé. Un `over 2.5` gagné à 1.35 et le même marché gagné à 2.20 n'ont pas la même valeur pour la calibration.

## Commande de génération

```bash
python historical_dataset_builder.py --from 2025-05-18 --to 2026-05-18 --output data/historical_backtest.csv
```

Le CSV final contient :

```csv
date,home,away,competition,market_type,pari,odds,result,bookmaker,source,visible
```

Colonnes optionnelles préparées pour de futurs enrichissements :

```csv
confidence,danger,value_score,ev_pct,p_market,p_fused,edge_pct,decision
```

## Import dans la mémoire Oracle Bot

Pour générer puis importer automatiquement dans PostgreSQL si `DATABASE_URL` existe, ou dans la mémoire locale sinon :

```bash
python historical_dataset_builder.py --from 2025-05-18 --to 2026-05-18 --output data/historical_backtest.csv --import
```

Le flag `--import` réutilise la logique de `backtest_import.py`, donc l'import passe par `save_db()`.

## Sources utilisées

Résultats :

- `FOOTBALL_DATA_KEY` pour football-data.org.
- `FOOTBALL_KEY`, `API_FOOTBALL_KEY` ou `APISPORTS_KEY` pour API-Football.

Cotes historiques :

- `ODDSPAPI_KEY`, `ODDS_API_KEY` ou `THE_ODDS_API_KEY` pour The Odds API historique.

## Limites des APIs gratuites

Les résultats historiques sont souvent disponibles plus facilement que les cotes historiques. The Odds API expose un endpoint historique, mais il peut nécessiter un plan payant. Si l'API répond `401`, `402`, `403` ou `422`, le script affiche un warning clair et continue sans inventer de cotes.

Dans ce cas, le CSV peut ne contenir que l'en-tête, ce qui est volontaire et préférable à un dataset trompeur.

## Ajouter un fournisseur de cotes plus tard

Le script contient une interface simple :

```python
get_historical_odds(match, market_type) -> odds or None
```

Pour ajouter un fournisseur comme oddspapi.io ou sportsgameodds :

1. Créer une classe qui hérite de `HistoricalOddsProvider`.
2. Implémenter `get_match_odds(match)` en retournant uniquement des cotes réelles.
3. Normaliser les marchés vers `h2h_home`, `h2h_away`, `draw`, `over25`, `under25`, `btts_yes`, `btts_no`.
4. Ne jamais retourner de cote par défaut si le fournisseur ne l'a pas fournie.
