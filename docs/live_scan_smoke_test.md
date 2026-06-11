# Live Scan Smoke Test V9.6

`live_scan_smoke_test.py` diagnostique le scan API-Football aujourd'hui/demain sans ecrire dans le ledger et sans envoyer Telegram.

Commandes:

```bash
python live_scan_smoke_test.py --date YYYY-MM-DD --allow-network
python live_scan_smoke_test.py --date YYYY-MM-DD --days 2 --allow-network --debug
```

Sorties:

- `reports/live_scan_smoke_test_YYYY-MM-DD.json`
- `reports/live_scan_smoke_test_YYYY-MM-DD.html`

Le reseau reste bloque sans `--allow-network`. Le smoke test explique les cas `fixtures=0`, `odds_valid=0` ou `h2h_non_termines=0` sans modifier `reports/shadow_ledger.csv`.
