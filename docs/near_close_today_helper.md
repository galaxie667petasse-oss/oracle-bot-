# V9.2 Near-Close Today Helper

`near_close_today_helper.py` lit le shadow ledger et liste les observations du jour qui attendent une closing odds. Il ne collecte rien et ne lance aucun reseau; il produit seulement les commandes humaines possibles.

Commande:

```bash
python near_close_today_helper.py --ledger reports/shadow_ledger.csv --sport-map config/sport_key_map.example.json --date 2026-06-04 --output reports/near_close_today.json
```

Le rapport affiche:

- observations du jour sans closing;
- ligues concernees;
- sport keys The Odds API si connues;
- fixture ids API-Football extraits des notes `source_event_id=...`;
- commandes near-close suggerees;
- fallback manuel Betclic.

Les commandes suggerees peuvent inclure `--allow-network`, mais le helper ne les execute jamais. Une near-close doit rester horodatee et matchable; elle ne doit pas etre inventee ni reutilisee comme taken odds.
