# V9.2 API-Football Odds Enrichment

API-Football odds peut renvoyer des lignes de cotes sans noms d'equipes exploitables. V9.2 ajoute un enrichissement prudent par fixtures: les odds gardent leur `source_event_id`, puis les equipes, la ligue, la date, le kickoff et le statut sont ajoutes depuis un CSV/JSON fixtures deja disponible.

Commandes locales:

```bash
python api_football_odds_adapter.py --from-fixture reports/api_football_odds_raw.json --fixtures-csv reports/api_football_fixtures.csv --valid-only --market h2h --one-side-per-event --max-events 3 --output reports/api_football_odds_enriched.csv --output-invalid reports/api_football_odds_invalid.csv --summary-json reports/api_football_odds_summary.json --html reports/api_football_odds_summary.html
python api_football_valid_odds_selector.py --odds reports/api_football_odds_enriched.csv --output reports/api_football_shadow_selection.csv --summary-json reports/api_football_shadow_selection_summary.json --max-events 3
```

Regles:

- aucun reseau sans `--allow-network`;
- `--dry-run` ne lance aucun reseau;
- les lignes sans equipe restent invalides;
- les cotes 0-1 sont rejetees comme probabilites probables;
- les near-close ne sont pas converties en taken odds;
- les selections restent `observation shadow` ou `watchlist`, jamais une activation.

L'enrichissement aide a rendre les odds matchables au shadow ledger. Il ne prouve pas la CLV, ne remplace pas une closing odds reelle et ne valide aucune strategie.

## V9.3 Debug

Quand un CSV enrichi existe deja, le diagnostic rapide est:

```bash
python api_football_odds_debug_report.py --odds reports/api_football_odds_enriched_YYYY-MM-DD.csv --output reports/api_football_odds_debug_YYYY-MM-DD.json --html reports/api_football_odds_debug_YYYY-MM-DD.html
```

Le rapport montre les markets, sides, bookmakers, status, H2H valides et exemples de candidates. Il sert a comprendre pourquoi le selector retient 0, 1, 2 ou 3 observations.
