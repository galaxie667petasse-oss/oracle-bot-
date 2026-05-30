# V8.3 Odds Source Lab

## Objectif

Le laboratoire de sources de cotes prepare la collecte propre des cotes live ou near-close sans activer de reseau automatiquement. Il separe trois objets :

- `taken odds` : cote observee au moment ou une observation shadow est notee ;
- `near-close odds` : snapshot proche du coup d'envoi, utile pour diagnostic si le timestamp est fiable ;
- `true historical closing odds` : closing line historique documentee, seule base solide pour une CLV robuste.

## Sources supportees

- CSV manuel : option gratuite immediate, controlee par l'utilisateur.
- API-Football : adaptateur pret, aucun appel reseau sans `--allow-network`.
- The Odds API : adaptateur pret, aucun appel reseau sans `--allow-network`.

Les API gratuites servent surtout a tester le pipeline et la couverture. Elles ne prouvent pas automatiquement une closing line historique fiable.

## Workflow minimal

```bash
python odds_source_config.py --write-example
python odds_source_config.py --check
python manual_odds_import.py --template reports/manual_odds_snapshot_template.csv
python manual_odds_import.py --input reports/manual_odds_snapshot.csv --store reports/odds_snapshots.csv
python odds_source_quality_report.py --snapshots reports/odds_snapshots.csv --output reports/odds_source_quality.json --html reports/odds_source_quality.html
```

## Regles de securite

- aucune cle API dans Git ;
- aucune ecriture dans `data/` ;
- snapshots dans `reports/` ;
- aucune mise conseillee ;
- aucune cote closing inventee ;
- toute modification du shadow ledger passe par un dry-run par defaut dans `oracle_ops.py`.

## Pourquoi ce lab existe

`data/MATCHES.csv` contient des colonnes `C_LTH/C_LTA`, mais V7.8 a montre que leurs valeurs ressemblent a des probabilites ou codes entre 0 et 1, pas a des cotes decimales. Il faut donc capturer ou importer des cotes fiables ailleurs avant de parler de CLV.

## V8.4 : workflow praticable

V8.4 ajoute :

- `odds_lab_wizard.py` pour guider les commandes ;
- `manual_odds_import.py --rejects-output --summary-json --strict` ;
- `odds_snapshot_store.py --validate --filter --near-close-only` ;
- `odds_intake_audit.py` pour verifier la chaine complete ;
- `odds_e2e_demo.py` pour tester le workflow sans vraie donnee.

Le principe important : les snapshots `is_near_close=true` ne sont jamais convertis en taken odds par defaut.
