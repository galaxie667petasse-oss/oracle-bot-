# Operations Center V8.2

## Objectif

`oracle_ops.py` regroupe les commandes quotidiennes du projet en un centre de controle local. Il ne lance aucun reseau, ne modifie pas `data/`, ne touche pas a `oracle_db.json` et ne declenche aucun Telegram.

## Commandes principales

```bash
python oracle_ops.py --health
python oracle_ops.py --daily
python oracle_ops.py --shadow-init
python oracle_ops.py --shadow-summary
python oracle_ops.py --shadow-report
python oracle_ops.py --shadow-templates
python oracle_ops.py --evidence
python oracle_ops.py --big5-summary
python oracle_ops.py --clv-readiness
python oracle_ops.py --full-local
```

## Health

`--health` verifie :

- modules shadow presents ;
- `reports/` ignore ;
- `external_data/` ignore ;
- presence locale de `data/features_modern.csv` et `data/MATCHES.csv` ;
- ledger shadow present ;
- aucun demarrage Telegram ou Railway par le centre ops.

Les statuts sont `OK`, `warning` ou `bloquant`.

## Full local

`--full-local` enchaine :

1. health ;
2. resume shadow ;
3. audit qualite ledger ;
4. rapport shadow CLV ;
5. evidence gate ;
6. sample size plan ;
7. dashboard optionnel.

Le mode reste laboratoire : aucune mise conseillee, aucun envoi, aucune activation automatique.

## V8.3 Odds Source Lab dans oracle_ops

Commandes ajoutees :

```bash
python oracle_ops.py --odds-config
python oracle_ops.py --odds-template
python oracle_ops.py --odds-summary
python oracle_ops.py --odds-quality
python oracle_ops.py --odds-to-shadow
python oracle_ops.py --closing-match
python oracle_ops.py --odds-lab
```

Par defaut, `--odds-to-shadow` et `--closing-match` restent en dry-run. Utiliser `--apply` seulement apres verification humaine. Aucun reseau n'est lance par ces commandes.

## V8.4 Odds intake

Commandes ajoutees :

```bash
python oracle_ops.py --odds-status
python oracle_ops.py --odds-wizard
python oracle_ops.py --odds-validate-manual reports/manual_odds_snapshot.csv
python oracle_ops.py --odds-import-manual reports/manual_odds_snapshot.csv --apply
python oracle_ops.py --odds-intake-audit
python oracle_ops.py --odds-next
```

Sans `--apply`, l'import manuel via ops reste une validation/dry-run.

## V8.5 Project blueprint

Commandes ajoutees :

```bash
python oracle_ops.py --architecture
python oracle_ops.py --contracts
python oracle_ops.py --scorecard
python oracle_ops.py --progress
python oracle_ops.py --llm-contract
python oracle_ops.py --agent-dryrun
python oracle_ops.py --project-map
```

Ces commandes decrivent l'architecture, les contrats, la scorecard et la boucle progressive. Elles restent locales : aucun reseau, aucun Telegram, aucune modification de `data/`.

## V8.6 matchday operations

```bash
python oracle_ops.py --real-start
python oracle_ops.py --matchday --date 2026-06-01
python oracle_ops.py --matchday-status reports/matchday_2026_06_01
python oracle_ops.py --matchday-report reports/matchday_2026_06_01
python oracle_ops.py --archive-tests --apply
```

Sans `--apply`, les operations sensibles restent en verification. Le but est de preparer la collecte reelle, pas d'activer une action automatique.
## V8.7 matchday operations

Operations Center expose les controles matchday phase-aware :

```bash
python oracle_ops.py --matchday-precheck reports/matchday_2026_06_01
python oracle_ops.py --matchday-next reports/matchday_2026_06_01
python oracle_ops.py --matchday-phase reports/matchday_2026_06_01 --phase pre_match
```

Ces commandes ne lancent aucun reseau et ne modifient pas `data/`. Elles servent a savoir quelle saisie humaine manque encore.

## V8.8 API odds operations

Commandes ajoutees :

```bash
python oracle_ops.py --scan-soccer-odds
python oracle_ops.py --api-odds-status
python oracle_ops.py --api-pre-match-jleague
python oracle_ops.py --near-close-status
python oracle_ops.py --near-close-next
python oracle_ops.py --real-guard-ledger
```

`--api-pre-match-jleague` affiche une commande dry-run a relancer manuellement dans `api_odds_collection_runner.py`. Aucun reseau n'est lance par `oracle_ops.py`.

## V8.9 shadow ops

Commandes ajoutees :

```bash
python oracle_ops.py --lifecycle
python oracle_ops.py --near-close-schedule
python oracle_ops.py --results-template
python oracle_ops.py --shadow-progress
python oracle_ops.py --odds-autopilot
```

Ces commandes restent locales. Elles servent a finir les observations ouvertes : near-close, resultats, evidence gate.

## V9.0 Source Coverage

Commandes utiles :

```powershell
python oracle_ops.py --active-soccer-sports
python oracle_ops.py --source-coverage
python oracle_ops.py --api-football-fixtures --date YYYY-MM-DD
python oracle_ops.py --api-football-matchday --date YYYY-MM-DD
python oracle_ops.py --manual-betclic-template --date YYYY-MM-DD
```

Ces commandes sont dry-run ou templates par defaut. Elles ne lancent pas de reseau et ne modifient pas `data/`.
## V9.1 Operations

`oracle_ops.py` expose les actions V9.1:

```powershell
python oracle_ops.py --external-evidence-catalog
python oracle_ops.py --historical-clv --historical-clv-file reports/historical_clv_import.csv
python oracle_ops.py --near-close-batch
python oracle_ops.py --proof-dashboard
python oracle_ops.py --evidence-acceleration
python oracle_ops.py --api-football-results --date 2026-06-03
```

Ces commandes ne lancent pas de reseau. `--api-football-results` dans `oracle_ops` affiche seulement la commande dry-run utile.

## V9.2 Same-Day Operations

Nouvelles actions locales:

```bash
python oracle_ops.py --api-football-same-day --date 2026-06-04
python oracle_ops.py --api-football-valid-odds --odds-csv reports/api_football_odds_enriched.csv
python oracle_ops.py --near-close-today --date 2026-06-04
```

Ces actions ne lancent aucun reseau par elles-memes. Elles servent a verifier l'etat de la journee, preparer une selection shadow limitee et lister les near-close a collecter humainement.

## V9.3 Same-Day Debug

Action locale ajoutee:

```bash
python oracle_ops.py --api-football-same-day-debug --date 2026-06-04
python oracle_ops.py --api-football-same-day-debug --odds-csv reports/api_football_odds_enriched_2026-06-04.csv
```

Elle lit seulement un CSV enrichi existant. Si le fichier manque, elle affiche la commande `api_football_same_day_runner.py --dry-run --debug` a relancer.
## V9.4 Operations Automation

Les commandes `oracle_ops.py --next-days`, `--near-close-window`, `--post-match-results`, `--football-data-import`, `--subscription-evaluator` et `--daily-ops` ajoutent un centre de controle pour juin.

Par defaut, ces actions restent en dry-run ou en lecture seule. Le reseau exige toujours une commande explicite avec `--allow-network` dans le runner concerne. L'apply ledger reste separe.
## V9.5 Telegram read-only

`oracle_ops.py` expose maintenant:

```bash
python oracle_ops.py --telegram-check
python oracle_ops.py --telegram-preview
python oracle_ops.py --telegram-daily
python oracle_ops.py --telegram-results
python oracle_ops.py --telegram-ops
```

Ces commandes restent en preview/dry-run par defaut. L'emission reelle demande `--allow-send` et une configuration locale valide. Telegram ne change pas la decision: evidence gate reste l'autorite, et les messages restent des observations shadow non validees.

## V9.6 Live scan et scheduler Windows

V9.6 corrige la propagation de `--allow-network` dans `api_football_next_days_runner.py` et `daily_operations_runner.py`. Le reseau est autorise seulement si le flag est present, tandis que l'ecriture ledger reste separee par dry-run/apply.

Commandes de diagnostic:

```bash
python api_football_next_days_runner.py --start-date YYYY-MM-DD --days 2 --allow-network --debug-network --max-events-per-day 2 --max-total-events 3
python live_scan_smoke_test.py --date YYYY-MM-DD --days 2 --allow-network --debug
python telegram_pipeline_smoke_test.py --date YYYY-MM-DD --dry-run
```

Les scripts Windows dans `scripts/` sont des preparations uniquement. Ils ne contiennent pas de token et gardent l'envoi Telegram derriere `ORACLE_ALLOW_TELEGRAM_SEND=true`.
