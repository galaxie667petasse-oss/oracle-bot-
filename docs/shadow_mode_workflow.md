# Shadow Mode Workflow V8.1

## Pourquoi utiliser le shadow mode

`data/MATCHES.csv` ne fournit pas actuellement de closing odds decimales fiables. Le shadow mode sert donc a collecter une preuve live propre : cote observee, raison du signal, closing odds manuelle fiable, resultat, puis CLV.

Ce n'est pas un systeme de mise. C'est un carnet de laboratoire.

## Initialiser

```bash
python shadow_workflow.py --init
```

Cette commande cree le ledger et les templates CSV dans `reports/`.

## Ajouter une observation a la main

```bash
python shadow_ledger.py --add --match-date 2026-06-01 --league EPL --home "Arsenal" --away "Chelsea" --market h2h --side home --taken-odds 2.10 --bookmaker manual --strategy-name test_signal --reason "observation shadow"
```

Le statut reste `observation`, `watchlist` ou `rejected`.

## Ajouter plusieurs observations par CSV

Creer le template :

```bash
python shadow_templates.py --candidates-template reports/shadow_candidates_template.csv
```

Importer le CSV rempli :

```bash
python shadow_ledger.py --add-csv reports/shadow_candidates_manual.csv
```

Les doublons sont ignores par defaut. Utiliser `--allow-duplicates` seulement pour un audit explicite.

## Creer et remplir le template closing

```bash
python shadow_workflow.py --make-closing-template
```

Remplir uniquement les closing odds reelles et decimales dans `reports/manual_closing_import_template.csv`, puis importer :

```bash
python closing_manual_import.py --ledger reports/shadow_ledger.csv --closing-csv reports/manual_closing_import.csv
```

Sans closing odds fiable, la CLV reste non calculable.

## Importer les resultats

Creer le template :

```bash
python shadow_templates.py --results-template reports/manual_results_import_template.csv --ledger reports/shadow_ledger.csv
```

Importer :

```bash
python results_manual_import.py --ledger reports/shadow_ledger.csv --results-csv reports/manual_results_import.csv
```

Resultats autorises : `win`, `loss`, `push`, `void`, `unknown`.

## Lire le rapport CLV

```bash
python shadow_clv_report.py --ledger reports/shadow_ledger.csv --output reports/shadow_clv_report.json --html reports/shadow_clv_report.html
```

Lire en priorite :

- coverage CLV ;
- CLV moyenne ;
- taux CLV positive ;
- ROI unite ;
- profit unite ;
- max drawdown ;
- splits par ligue, marche, side, strategie, bookmaker et mois ;
- warnings de sample.

## Runner quotidien

```bash
python report_runner.py --daily-shadow
```

Ce runner regenere les templates, le rapport shadow, la gouvernance et le dashboard si possible. Il ne lance aucun reseau et ne modifie pas `data/`.

## Seuils avant de croire un signal

- sample superieur a 1000 ;
- CLV moyenne positive ;
- ROI positif ;
- drawdown raisonnable ;
- stabilite par ligue et par marche ;
- pas de multiple testing non corrige ;
- validation historique coherente.

Avant ces conditions, le verdict reste `not_validated`, `observation_only` ou `watchlist`.

## Utilisation pour les matchs de juin

1. Creer 5-10 observations shadow de test.
2. Noter la cote prise et la source.
3. Attendre la closing line reelle.
4. Importer la closing manuelle.
5. Importer le resultat.
6. Relire le rapport.
7. Ne conclure qu'apres un sample significatif.

Aucun Telegram, aucun Railway, aucune mise automatique.

## V8.2 Operations Center

Pour eviter de memoriser toutes les commandes, utiliser :

```bash
python oracle_ops.py --health
python oracle_ops.py --daily
python report_runner.py --ops
```

Le workflow V8.2 ajoute :

- audit qualite ledger ;
- evidence gate ;
- sample size planner ;
- preview texte sans envoi ;
- runbook de juin.

Le statut final reste non valide tant que sample, CLV, resultats et qualite ledger ne sont pas suffisants.

## V8.3 : intake de cotes vers shadow

Le shadow workflow peut maintenant recevoir des snapshots normalises :

```bash
python manual_odds_import.py --input reports/manual_odds_snapshot.csv --store reports/odds_snapshots.csv
python odds_to_shadow.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --dry-run
python odds_closing_matcher.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --dry-run
```

Cette automatisation ne produit que des observations shadow. Elle ne valide pas un signal et ne cree aucune mise.
