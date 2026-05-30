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
