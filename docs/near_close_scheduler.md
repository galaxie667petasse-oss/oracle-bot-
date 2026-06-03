# Near-Close Scheduler V8.9

## Objectif

`near_close_scheduler.py` regroupe les observations sans closing par ligue et genere les commandes near-close adaptees au sport key The Odds API.

Le scheduler n'appelle jamais le reseau. Il imprime seulement les commandes.

## Mapping

Le mapping exemple est dans `config/sport_key_map.example.json` :

- J League -> `soccer_japan_j_league`
- Primera Division - Chile -> `soccer_chile_campeonato`
- Super League - China -> `soccer_china_superleague`
- Allsvenskan - Sweden -> `soccer_sweden_allsvenskan`
- Eliteserien - Norway -> `soccer_norway_eliteserien`

## Commandes

```bash
python near_close_scheduler.py --ledger reports/shadow_ledger.csv --commands
python near_close_scheduler.py --ledger reports/shadow_ledger.csv --output reports/near_close_schedule.json --html reports/near_close_schedule.html
```

Une commande collect near-close utilise `--allow-network`, mais elle doit rester lancee manuellement par l'utilisateur.
