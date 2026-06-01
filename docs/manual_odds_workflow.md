# V8.4 Manual Odds Workflow

## But

Ce workflow permet de collecter manuellement des cotes prises et des cotes near-close, sans reseau et sans conseil actif.

## Routine simple

```bash
python odds_lab_wizard.py --make-templates
```

Remplir ensuite `reports/manual_odds_snapshot.csv` avec :

- une ligne `is_near_close=false` pour la cote observee ;
- une ligne `is_near_close=true` pour la cote proche du coup d'envoi ;
- le meme match, marche, side et bookmaker si possible.

Valider :

```bash
python odds_lab_wizard.py --validate-manual reports/manual_odds_snapshot.csv
```

Importer :

```bash
python odds_lab_wizard.py --import-manual reports/manual_odds_snapshot.csv --apply
```

Convertir en shadow seulement apres controle :

```bash
python odds_to_shadow.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --dry-run
```

## Regles

- les valeurs 0-1 sont rejetees ;
- les cotes doivent etre decimales ;
- les near-close ne deviennent pas des taken odds par defaut ;
- toute ecriture ledger passe par une action explicite ;
- aucune mise n'est creee.

## Contrats V8.5

Avant import, le CSV manuel doit respecter le contrat `odds_snapshot` apres normalisation. Le ledger respecte le contrat `shadow_ledger`.

```bash
python pipeline_contracts.py --show odds_snapshot
python pipeline_contracts.py --show shadow_ledger
```

La restitution finale doit rester une observation shadow ou un refus tant que la preuve est insuffisante.
