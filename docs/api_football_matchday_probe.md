# V9.0 API-Football Matchday Probe

API-Football est utilise comme source de fixtures et comme diagnostic odds optionnel.

Regles:

- aucun reseau sans `--allow-network`;
- cle lue depuis l'environnement, jamais affichee;
- reponses vides et erreurs HTTP deviennent des warnings lisibles;
- si les fixtures existent mais les odds sont absentes, le manuel Betclic peut etre requis.

Commandes:

```powershell
python api_football_fixtures_adapter.py --dry-run --date 2026-06-03
python api_football_matchday_probe.py --dry-run --date 2026-06-03
python api_football_fixtures_adapter.py --allow-network --date YYYY-MM-DD --output reports/api_football_fixtures_YYYY_MM_DD.csv --raw-output reports/api_football_fixtures_YYYY_MM_DD.json
python api_football_matchday_probe.py --allow-network --date YYYY-MM-DD --output reports/api_football_matchday_probe_YYYY_MM_DD.json --html reports/api_football_matchday_probe_YYYY_MM_DD.html
```

Une cote API-Football n'est pas une closing odds fiable par defaut.

## V9.2 Enrichment

Le probe affiche maintenant les odds valides avant et apres enrichment fixtures, les events H2H valides, les events encore sans equipes, la couverture bookmaker et une action recommandee.

Si les fixtures existent mais que les odds restent invalides, le rapport oriente vers l'intake manuel. Si des H2H valides existent, l'action prudente est de lancer `api_football_same_day_runner.py` en dry-run puis de revoir la selection humaine.

```bash
python api_football_matchday_probe.py --date 2026-06-04 --from-fixtures reports/api_football_fixtures_2026_06_04.json --from-odds reports/api_football_odds_2026_06_04.json --output reports/api_football_matchday_probe.json --html reports/api_football_matchday_probe.html
```
