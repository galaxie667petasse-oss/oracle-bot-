# The Odds API Sport Scanner V8.8

## Sport keys suivies

Le scanner surveille notamment :

- `soccer_epl`
- `soccer_france_ligue_one`
- `soccer_germany_bundesliga`
- `soccer_italy_serie_a`
- `soccer_spain_la_liga`
- `soccer_uefa_champs_league`
- `soccer_uefa_europa_league`
- `soccer_japan_j_league`
- `soccer_norway_eliteserien`
- `soccer_sweden_allsvenskan`
- `soccer_usa_mls`

## Utilisation

```bash
python soccer_odds_sport_scanner.py --dry-run
python soccer_odds_sport_scanner.py --from-fixtures tests/fixtures --sports soccer_japan_j_league --output reports/soccer_odds_sport_scan.json --html reports/soccer_odds_sport_scan.html
```

Le scan reseau reel demande :

```bash
python soccer_odds_sport_scanner.py --allow-network --sports soccer_japan_j_league --output reports/soccer_odds_sport_scan.json --html reports/soccer_odds_sport_scan.html
```

## Lecture

Le rapport indique les sports actifs, les bookmakers detectes, les marches trouves, les dates de match et une priorite de collecte. Il ne declenche aucune observation shadow automatiquement.
