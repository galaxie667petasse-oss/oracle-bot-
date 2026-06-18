# Telegram Near-Close Reporter

V9.7 ajoute `telegram_near_close_reporter.py` pour publier en Telegram read-only qu'une near-close a ete capturee.

Le reporter ne choisit aucun match et ne conseille aucune mise. Il lit uniquement une observation deja presente dans le ledger.

Garde-fous:

- dry-run par defaut ;
- envoi reel seulement avec `--allow-send` ;
- tracking anti-doublon dans `reports/telegram_published_near_close.json` ;
- `--force` permet une republication volontaire ;
- aucun Telegram reel dans les tests ;
- `lab_only=true` et `can_influence_picks=false`.

Commandes:

```bash
python telegram_near_close_reporter.py --ledger reports/shadow_ledger.csv --shadow-id sh_20260617210447_2ee081d9 --dry-run
python telegram_near_close_reporter.py --ledger reports/shadow_ledger.csv --shadow-id sh_20260617210447_2ee081d9 --allow-send --plain-text
```

Message type:

```text
ORACLE SHADOW LAB - NEAR-CLOSE CAPTUREE
Match : Ghana - Panama
Observation : h2h home
Cote prise : 2.26
Cote near-close : 2.26
CLV : 0.00%
Qualite : same_bookmaker
Statut : resultat en attente
Aucune mise. Laboratoire local uniquement.
```

