# API-Football Near-Close Apply

V9.7 ajoute `api_football_near_close_apply.py` pour appliquer une near-close API-Football deja capturee dans un CSV au `reports/shadow_ledger.csv`.

Le module est local et prudent:

- dry-run par defaut ;
- ecriture ledger seulement avec `--apply` ;
- matching par `source_event_id` / `fixture_id`, `market_type`, `side`, puis bookmaker si disponible ;
- jamais de matching par noms d'equipes seuls ;
- aucune cle API requise ;
- aucun reseau ;
- aucune mise, aucun pick automatique.

Commandes:

```bash
python api_football_near_close_apply.py --ledger reports/shadow_ledger.csv --near-close-file reports/api_football_near_close_1489385.csv --dry-run
python api_football_near_close_apply.py --ledger reports/shadow_ledger.csv --near-close-file reports/api_football_near_close_1489385.csv --shadow-id sh_20260617210447_2ee081d9 --dry-run
python api_football_near_close_apply.py --ledger reports/shadow_ledger.csv --near-close-file reports/api_football_near_close_1489385.csv --shadow-id sh_20260617210447_2ee081d9 --apply
```

Champs ledger ajoutes si absents:

- `closing_odds`
- `closing_bookmaker`
- `closing_source`
- `closing_captured_at`
- `closing_fixture_id`
- `closing_quality`
- `clv`
- `clv_pct`
- `closing_status`

Qualites possibles: `same_bookmaker`, `cross_bookmaker_same_market`, `best_available_same_market`, `manual_unverified`, `unavailable`.

Statuts possibles: `captured`, `missing`, `ambiguous`, `overdue_missing`.

Pour Ghana - Panama, la cote prise `2.26` et la cote near-close `2.26` donnent `clv=0.0` et `clv_pct=0.0`.

