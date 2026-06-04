# V9.2 API-Football Same-Day Runner

`api_football_same_day_runner.py` orchestre une journee API-Football en laboratoire local:

1. charger les fixtures du jour depuis un JSON/CSV ou, uniquement avec `--allow-network`, depuis API-Football;
2. charger les odds du jour;
3. enrichir les odds avec les fixtures;
4. selectionner quelques lignes H2H valides;
5. simuler la conversion vers le shadow ledger en dry-run par defaut.

Commande sans reseau:

```bash
python api_football_same_day_runner.py --date 2026-06-04 --dry-run
```

Commande avec fixtures/odds locales:

```bash
python api_football_same_day_runner.py --date 2026-06-04 --fixtures-json reports/api_football_fixtures_2026_06_04.json --odds-json reports/api_football_odds_2026_06_04.json --output-dir reports/api_football_same_day_2026_06_04 --max-events 3 --prefer-side home
```

Sorties dans `reports/`:

- `fixtures.csv`;
- `odds_enriched.csv`;
- `odds_invalid.csv`;
- `odds_summary.json/html`;
- `selection.csv`;
- `selection_summary.json`;
- `dry_run_shadow.json`;
- `summary.json/html`.

Le mode `--apply` est volontairement separe. Le runner ne fait aucune mise, aucun Telegram, aucun Railway et ne modifie pas `data/`.
