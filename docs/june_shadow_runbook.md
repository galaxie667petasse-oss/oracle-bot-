# June Shadow Runbook

## Routine quotidienne matin

1. Lancer `python oracle_ops.py --health`.
2. Lancer `python oracle_ops.py --daily`.
3. Verifier les observations shadow du jour.
4. Generer les templates si besoin.
5. Ne rien conclure avant CLV et resultats.

## Avant match

1. Noter le match, la ligue, le marche et le side.
2. Noter la cote prise observee.
3. Noter le bookmaker/source.
4. Ecrire la raison en langage descriptif.
5. Garder le statut `observation` ou `watchlist`.

Commande possible :

```bash
python shadow_ledger.py --add --match-date 2026-06-01 --league EPL --home "Arsenal" --away "Chelsea" --market h2h --side home --taken-odds 2.10 --bookmaker manual --strategy-name test_signal --reason "observation shadow"
```

## Apres match

1. Remplir la closing odds manuelle si elle vient d'une source fiable.
2. Importer la closing :

```bash
python closing_manual_import.py --ledger reports/shadow_ledger.csv --closing-csv reports/manual_closing_import.csv
```

3. Remplir le resultat.
4. Importer le resultat :

```bash
python results_manual_import.py --ledger reports/shadow_ledger.csv --results-csv reports/manual_results_import.csv
```

## Rapport quotidien

```bash
python shadow_quality_audit.py --ledger reports/shadow_ledger.csv --output reports/shadow_quality_audit.json --html reports/shadow_quality_audit.html
python shadow_clv_report.py --ledger reports/shadow_ledger.csv --output reports/shadow_clv_report.json --html reports/shadow_clv_report.html
python evidence_gate.py --shadow-report reports/shadow_clv_report.json --quality-audit reports/shadow_quality_audit.json --big5-summary reports/big5_xg_summary.json --clv-readiness reports/clv_readiness.json --output reports/evidence_gate.json --html reports/evidence_gate.html
python sample_size_planner.py --shadow-report reports/shadow_clv_report.json --output reports/sample_size_plan.json --html reports/sample_size_plan.html
```

## Quand ignorer une observation

- cote absente ou non decimale ;
- closing odds non fiable ;
- match mal identifie ;
- marche ou side ambigu ;
- information post-match utilisee ;
- raison trop vague ;
- doublon probable.

## Regles de prudence

- aucune mise ;
- pas de Telegram public ;
- pas de conclusion avant sample significatif ;
- CLV obligatoire ;
- sample > 1000 minimum ;
- ROI seul ne suffit pas ;
- pas de Kelly reel ;
- pas de promesse de rentabilite.

## Exemple de journee complete

1. Matin : `oracle_ops.py --daily`.
2. Avant match : ajouter 2-3 observations shadow.
3. Apres closing : remplir `manual_closing_import.csv`.
4. Apres resultats : remplir `manual_results_import.csv`.
5. Soir : relancer `report_runner.py --ops --skip-dashboard`.
6. Lire `evidence_gate.html`.
7. Continuer la collecte si le statut est non valide.

## Ajout V8.3 : snapshots de cotes

Routine supplementaire pour juin :

1. Generer `reports/manual_odds_snapshot_template.csv`.
2. Renseigner quelques cotes observees avec timestamp.
3. Importer vers `reports/odds_snapshots.csv`.
4. Lire `odds_source_quality_report.py`.
5. Convertir en observations shadow seulement apres controle.
6. Noter un snapshot `is_near_close=true` si proche du coup d'envoi.
7. Matcher ce snapshot vers le ledger en dry-run.

Un snapshot near-close aide le diagnostic, mais ne remplace pas une vraie source closing historique documentee.

## Routine V8.4 recommandee

```bash
python odds_lab_wizard.py --status
python odds_lab_wizard.py --make-templates
python odds_lab_wizard.py --validate-manual reports/manual_odds_snapshot.csv
python odds_lab_wizard.py --dry-run-full
python odds_intake_audit.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --output reports/odds_intake_audit.json --html reports/odds_intake_audit.html
```

Lire d'abord les rejets et les ambiguites. Appliquer seulement apres verification humaine.

## Routine V8.5 blueprint

En fin de journee, journaliser la boucle :

```bash
python progress_loop.py --add --phase mesurer --title "Rapport shadow du jour" --status done --notes "lecture evidence gate"
```

Relire la carte projet si le workflow devient confus :

```bash
python oracle_ops.py --project-map
```

Le LLM analyste reste explicatif : il ne remplace jamais les mesures, la CLV, le sample ou l'evidence gate.

## V8.6 collecte reelle

Avant une vraie journee de juin :

```bash
python test_archive_manager.py --status
python odds_lab_wizard.py --real-start
python matchday_pack.py --date 2026-06-01 --output-dir reports/matchday_2026_06_01
python matchday_runner.py --pack reports/matchday_2026_06_01 --full-dry-run
```

Routine :

- matin : preparer le pack et verifier que les tests sont archives ;
- avant match : remplir les taken odds reelles ;
- juste avant kickoff : remplir les near-close reelles ;
- apres match : renseigner les resultats ;
- fin de journee : lancer `matchday_runner.py --report` puis lire `evidence_gate.py`.

Ne jamais melanger demo/test/fictif et reel dans le meme cycle.
## V8.7 routine matchday phase-aware

Avant match :

```bash
python matchday_runner.py --pack reports/matchday_YYYY_MM_DD --full-dry-run --phase pre_match
```

Si une taken odds est valide, le dry-run doit simuler `staged_shadow_created=1` pour une ligne. Near-close absente est normale.

Proche du coup d'envoi :

```bash
python matchday_runner.py --pack reports/matchday_YYYY_MM_DD --full-dry-run --phase near_close
```

Apres match :

```bash
python matchday_runner.py --pack reports/matchday_YYYY_MM_DD --full-dry-run --phase post_match
```

Toujours relire `next_actions`. Le workflow reste observation shadow, sans mise.

## V8.8 API odds en journee

Si l'utilisateur choisit The Odds API, le reseau reste une action manuelle :

```bash
python soccer_odds_sport_scanner.py --dry-run
python the_odds_api_adapter.py --allow-network --sport soccer_japan_j_league --regions us,uk,eu --markets h2h --max-events 3 --one-side-per-event --output reports/the_odds_api_jleague_today.csv
python odds_shadow_selector.py --snapshots reports/the_odds_api_jleague_today.csv --output reports/api_shadow_selection.csv --summary-json reports/api_shadow_selection_summary.json --max-events 3 --one-side-per-event --prefer-side home
python odds_to_shadow.py --selection-csv reports/api_shadow_selection.csv --ledger reports/shadow_ledger.csv --dry-run
```

Avant kickoff, verifier les pending closing :

```bash
python near_close_workflow.py --ledger reports/shadow_ledger.csv --status
python near_close_workflow.py --ledger reports/shadow_ledger.csv --suggest-commands
```

Le guard reel doit cibler les observations du ledger :

```bash
python real_observation_guard.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --phase pre_match --scope ledger
```

Cette routine collecte des preuves. Elle ne cree aucune mise, aucun message Telegram et aucune conclusion rapide.

## V8.9 operations autonomes locales

Avant d'ajouter de nouvelles observations, verifier le cycle de vie :

```bash
python event_lifecycle_manager.py --ledger reports/shadow_ledger.csv --status
python near_close_scheduler.py --ledger reports/shadow_ledger.csv --commands
python odds_autopilot_dryrun.py --full
```

Si `pending closing` est eleve, la prochaine action humaine est la capture near-close. Si `pending results` est eleve :

```bash
python result_capture_helper.py --ledger reports/shadow_ledger.csv --template reports/manual_results_due.csv
```

Le but est de fermer les observations ouvertes, pas d'augmenter artificiellement le volume.

## V9.0 Routine source coverage

1. Decouvrir les sports actifs si une requete explicite est acceptable.
2. Scanner seulement les sport keys soccer actifs et proches.
3. Utiliser API-Football fixtures pour savoir quels matchs existent aujourd'hui.
4. Si les odds API manquent mais que le match est visible chez Betclic, utiliser `manual_betclic_intake_helper.py`.
5. Capturer la near-close plus tard avant toute lecture CLV.

Rappel : aucune mise, aucune conclusion avant sample significatif et evidence gate propre.
## V9.1 June Proof Loop

Routine ajoutee:

1. Lire `python oracle_ops.py --evidence-acceleration`.
2. Si un CSV historique closing fiable existe, lancer le schema detector puis l'import CLV.
3. Capturer les near-close manuelles ou preparer le batch near-close.
4. Importer les resultats finis via CSV ou adaptateur API-Football en dry-run.
5. Relancer `python report_runner.py --proof --skip-dashboard`.

La preuve historique aide a prioriser, mais ne remplace pas les observations shadow de juin.

## V9.2 Routine same-day API-Football

Routine prudente:

1. lancer `python api_football_same_day_runner.py --date YYYY-MM-DD --dry-run`;
2. si des fixtures/odds locales existent, les passer via `--fixtures-json` et `--odds-json`;
3. lire `selection.csv` avant toute ecriture ledger;
4. convertir avec `odds_to_shadow.py --selection-csv ... --dry-run`;
5. collecter la near-close plus tard avec `near_close_today_helper.py`;
6. matcher les resultats par `source_event_id` si disponible.

Si aucune cote valide n'apparait apres enrichment, utiliser le template manuel. Ne pas multiplier les observations si les near-close precedentes ne sont pas encore capturees.
