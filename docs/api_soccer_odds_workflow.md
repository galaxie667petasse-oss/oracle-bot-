# V8.8 API Soccer Odds Workflow

## Objectif

V8.8 prepare une collecte optionnelle The Odds API pour les ligues soccer utiles en juin. Le reseau reste coupe par defaut : un appel reel exige `--allow-network` dans la commande explicite de l'utilisateur.

Le workflow separe quatre etapes :

1. scanner les sport keys soccer disponibles ;
2. collecter un petit snapshot pre-match ;
3. selectionner peu d'observations shadow ;
4. capturer plus tard une near-close reelle pour calculer une CLV.

## Commandes offline

```bash
python soccer_odds_sport_scanner.py --dry-run
python api_odds_collection_runner.py --scan-sports --dry-run
python report_runner.py --api-odds --skip-dashboard
```

## Commande reseau manuelle

```bash
python the_odds_api_adapter.py --allow-network --sport soccer_japan_j_league --regions us,uk,eu --markets h2h --bookmaker Pinnacle --max-events 3 --one-side-per-event --output reports/the_odds_api_jleague_today.csv
```

Cette commande doit rester manuelle. Elle ne cree aucune observation shadow tant que l'utilisateur ne lance pas la selection puis la conversion.

## Regles

- ne pas appeler l'API sans `--allow-network` ;
- ne pas collecter toutes les issues par defaut ;
- ne pas melanger taken odds et near-close ;
- ne pas ecrire dans `data/` ;
- ne pas conclure sans CLV reelle et sample significatif.

## V8.9 protections pending closing

Avant d'ajouter plus de pre-match :

```bash
python api_odds_collection_runner.py --full-pre-match --avoid-existing-events --ledger reports/shadow_ledger.csv --no-apply-if-pending-closing-over 3
```

Si le ledger contient trop d'observations sans closing, le runner refuse l'apply et demande de capturer les near-close en priorite.
