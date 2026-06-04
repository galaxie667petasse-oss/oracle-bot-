# Near-Close Capture Workflow V8.8

## Principe

Une near-close est un snapshot capture pres du kickoff. Elle sert a renseigner `closing_odds` dans le shadow ledger si elle correspond exactement au match, marche et side.

Elle n'est jamais inventee et ne remplace jamais une taken odds.

## Routine

1. Verifier les observations en attente :

```bash
python near_close_workflow.py --ledger reports/shadow_ledger.csv --status
```

2. Afficher les commandes suggerees :

```bash
python near_close_workflow.py --ledger reports/shadow_ledger.csv --suggest-commands
```

3. Importer un fichier near-close deja capture :

```bash
python near_close_workflow.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --near-close-file reports/the_odds_api_jleague_near_close.csv --dry-run
```

4. Appliquer seulement apres verification :

```bash
python near_close_workflow.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --near-close-file reports/the_odds_api_jleague_near_close.csv --apply
```

## Guardrails

- `pre_match` : l'absence de near-close est normale ;
- `near_close` : une observation shadow attend une near-close correspondante ;
- ambiguite bookmaker/marche/side : pas de mise a jour automatique ;
- CLV calculee seulement avec cote decimale plausible.

## V8.9 scheduler

`near_close_scheduler.py` regroupe les observations pending par ligue :

```bash
python near_close_scheduler.py --ledger reports/shadow_ledger.csv --commands
```

Il ne lance pas le reseau. Il imprime seulement les commandes near-close a lancer manuellement.

## V9.0 Mapping sport keys

`near_close_scheduler.py` lit `config/sport_key_map.example.json` puis `config/sport_key_map.local.json` si present. Le fichier local permet d'ajouter une ligue sans committer de configuration personnelle.

Brazil Serie B, Finlande Veikkausliiga, Spain Segunda et Sweden Superettan sont prepares dans le mapping exemple.
