# V9.0 Active Sports Discovery

Objectif: decouvrir les competitions soccer actives The Odds API avant de scanner les cotes.

Le module `the_odds_active_sports.py` lit `/v4/sports` uniquement si `--allow-network` est fourni. En test et en dry-run, aucun reseau n'est lance.

Usage:

```powershell
python the_odds_active_sports.py --dry-run
python the_odds_active_sports.py --allow-network --group Soccer --output reports/the_odds_api_active_soccer_sports.json --html reports/the_odds_api_active_soccer_sports.html
```

Les marchés outright/winner doivent etre exclus du shadow intake pre-match. Ils servent au coverage source, pas a la creation d'observations match-level.

Mode laboratoire: aucune mise, aucun Telegram, aucune conclusion sans evidence gate.
