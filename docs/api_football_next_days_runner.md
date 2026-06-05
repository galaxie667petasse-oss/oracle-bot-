# V9.4 - API-Football Next Days Runner

`api_football_next_days_runner.py` scanne une fenetre future, par exemple demain ou les trois prochains jours, puis reutilise le pipeline same-day corrige en V9.3.

Regles:

- reseau bloque par defaut;
- `--allow-network` requis pour une vraie collecte;
- `--apply` requis pour ecrire dans le shadow ledger;
- si le ledger a plus de 20 closing pending, l'apply est bloque sauf `--force-lab`;
- selection H2H seulement par defaut, status `NS/TBD`, non live, non finished;
- laboratoire local, aucune mise.

Commande:

```bash
python api_football_next_days_runner.py --start-date YYYY-MM-DD --days 3 --allow-network --max-events-per-day 3
```
