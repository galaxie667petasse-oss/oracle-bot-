# V9.3 API-Football Same-Day Runner Fix

Le bug observe etait une incoherence entre deux chemins:

- `api_football_odds_adapter.py` recuperait les odds larges, enrichissait avec `fixtures.csv`, puis constatait des milliers de lignes valides;
- `api_football_same_day_runner.py` envoyait le filtre local `h2h` jusqu'a l'endpoint API-Football (`bet=h2h`), ce qui pouvait retourner 0 odds exploitables selon le format attendu par l'API.

Correction V9.3:

1. le runner recupere les odds larges;
2. il ecrit `fixtures.csv/json`;
3. il enrichit les odds avec `fixtures.csv`;
4. il ecrit `odds_enriched.csv`, `odds_invalid.csv`, `odds_summary.json/html`;
5. il lance le selector sur `odds_enriched.csv`;
6. le filtrage H2H/status/bookmaker se fait localement;
7. le runner ecrit `odds_debug.json` et `selection_debug.json`.

Commandes:

```bash
python api_football_odds_debug_report.py --odds reports/api_football_odds_enriched_YYYY-MM-DD.csv --output reports/api_football_odds_debug_YYYY-MM-DD.json --html reports/api_football_odds_debug_YYYY-MM-DD.html
python api_football_valid_odds_selector.py --odds reports/api_football_odds_enriched_YYYY-MM-DD.csv --market h2h --max-events 3 --one-side-per-event --output reports/api_football_shadow_selection.csv --summary-json reports/api_football_shadow_selection_summary.json --debug-summary-json reports/api_football_valid_odds_debug.json
python api_football_same_day_runner.py --date YYYY-MM-DD --dry-run --debug
```

Avec reseau explicite:

```bash
python api_football_same_day_runner.py --date YYYY-MM-DD --allow-network --max-events 3 --debug
```

Garde-fous:

- aucun reseau sans `--allow-network`;
- `--dry-run` empeche l'ecriture dans le ledger;
- FT/live/near-close sont exclus par defaut;
- si le status manque, le selector continue avec warning au lieu de tout rejeter;
- aucune observation shadow ne devient une recommandation active.
