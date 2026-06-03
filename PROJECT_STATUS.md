# Statut Oracle Football Bot

## Version actuelle

V8.9 Autonomous Odds Operations, Event Lifecycle Manager, Near-Close Scheduler & Evidence Dashboard.

Etat : local prudent. V7.0 Statistical Proof Foundation, V7.2 Understat xG Full Pipeline Quality Gate, V7.3 Multi-League Join Diagnostics, V7.4 Bundesliga Team Alias Expansion, V7.5 Big Five xG Aggregation, V7.6 Closing Odds Recovery, V7.7 Partial CLV Pipeline, V7.8 Closing Column Forensics et V8.0/V8.1 Shadow Mode restent en place. V8.2 ajoute un Operations Center, un audit qualite ledger, un evidence gate, un simulateur, un sample size planner, un formatter texte sans envoi et un June runbook. V8.3 ajoute le Odds Source Lab, les snapshots de cotes, les adaptateurs API optionnels et le matching near-close vers shadow ledger. V8.4 ajoute le wizard manuel, l'audit intake, la demo E2E synthetique et les garde-fous taken/near-close. V8.5 fixe la carte d'architecture canonique, les contrats de pipeline, le contrat LLM analyste, le schema de restitution, la boucle progressive et la scorecard projet. V8.6 ajoute l'archive de tests, le guard reel, le matchday pack, le matchday runner et les garde-fous de saisie humaine. V8.7 rend le matchday runner phase-aware et le full-dry-run predictif via staging temporaire. V8.8 ajoute le scanner soccer The Odds API, la selection shadow limitee, le workflow near-close et le guard scope ledger. V8.9 ajoute le lifecycle des observations, le scheduler near-close, le helper resultats, le dashboard progress et l'autopilot dry-run. Aucun signal robuste active. Aucun changement V8.9 ne branche Telegram, Railway ou un pick automatique.

V8.1 Shadow UX reste la base du workflow quotidien ; V8.2 ajoute le centre operations et le gate de preuve.

## Etat general

- Memoire moderne recommandee : 2015-2025.
- Volume connu : environ 528066 records regles.
- Feature matrix principale : `data/features_modern.csv`.
- Rapports locaux disponibles : backtest, favoris, stabilite, pricing, ML, External Dataset Lab, dashboard central.
- Probe Understat multi-saisons disponible, dependance `soccerdata` optionnelle.
- Export Understat EPL 2020-2025 attendu : 1900 lignes avec saisons explicites `2020-2021` a `2024-2025`.
- Quality gate xG disponible via `xg_dataset_quality.py`.
- Diagnostic jointure disponible via `join_diagnostics.py`.
- Alias Bundesliga, Serie A et Ligue 1 disponibles dans `team_name_normalizer.py`.
- Pipeline local Understat xG disponible via `understat_xg_pipeline.py`.
- Agregateur multi-ligue Big 5 disponible via `multi_league_xg_aggregator.py`.
- Rapport CLV readiness disponible via `clv_readiness_report.py`.
- Probe closing odds disponible via `closing_odds_probe.py`, lecture seule.
- Closing column forensics disponible : min/max/mediane/percentiles, exemples bruts, taux de valeurs plausibles et verdict par colonne.
- Shadow ledger local disponible via `shadow_ledger.py`.
- Import closing manuel disponible via `closing_manual_import.py`.
- Import resultats manuel disponible via `results_manual_import.py`.
- Templates CSV shadow disponibles via `shadow_templates.py`.
- Workflow quotidien shadow disponible via `shadow_workflow.py`.
- Rapport CLV shadow disponible via `shadow_clv_report.py`, avec ROI unite, profit, drawdown, splits et warnings sample.
- Candidats shadow quotidiens disponibles via `daily_shadow_candidates.py`, importables vers le ledger sans automatisation.
- Operations Center disponible via `oracle_ops.py`.
- Audit qualite ledger disponible via `shadow_quality_audit.py`.
- Evidence gate disponible via `evidence_gate.py`.
- Simulateur shadow disponible via `shadow_simulator.py`.
- Sample size planner disponible via `sample_size_planner.py`.
- Formatter texte shadow disponible via `shadow_message_formatter.py`, sans envoi Telegram.
- Architecture canonique disponible via `oracle_architecture_map.py`.
- Contrats de pipeline disponibles via `pipeline_contracts.py`.
- Contrat LLM analyste disponible via `llm_analyst_contract.py`, sans appel LLM reel.
- Schema de restitution disponible via `restitution_schema.py`.
- Boucle de progression disponible via `progress_loop.py`.
- Scorecard projet disponible via `oracle_project_scorecard.py`.
- Agent orchestrator dry-run disponible via `agent_orchestrator_dryrun.py`.
- Archive manager tests/demo disponible via `test_archive_manager.py`.
- Guard observations reelles disponible via `real_observation_guard.py`.
- Matchday pack disponible via `matchday_pack.py`.
- Matchday runner disponible via `matchday_runner.py`.
- Matchday status report disponible via `matchday_status_report.py`.
- Matchday runner phase-aware : `pre_match`, `near_close`, `post_match`, `full_day`.
- Full-dry-run staging : simulation temporaire taken -> snapshot -> shadow -> closing -> resultats sans modifier le store reel.
- Preview features closing disponible via `features_closing_enricher.py`, sortie limitee a `reports/`.
- CLV partielle H2H home/away disponible uniquement si la closing exacte du cote joue existe.
- CLV / Closing Line Value disponible si des cotes closing sont presentes.
- Reliability curves disponibles via `calibration_report.py`.
- Validation statistique disponible via `statistical_validation.py`.
- Benchmark gouvernance V8.0 disponible.
- Aucun signal robuste active et aucun candidat robuste sans CLV positive.
- Railway/Telegram toujours en attente.

## Vrai blocage

Le vrai blocage n'est pas le bankroll management. Le blocage est :

- CLV absente ou non prouvee sur les strategies ;
- preuve statistique insuffisante ;
- bootstrap ROI 5e percentile souvent non valide ;
- multiple testing dangereux sur des dizaines de segments ;
- CLV + preuve statistique + stabilite annuelle restent necessaires meme si xG ameliore Brier/log loss ;
- xG multi-saisons Understat doit etre transforme en rolling pre-match sans fuite ;
- Bundesliga exportait correctement mais jointait trop faiblement a xgabora avant alias, ce qui justifiait le blocage strict ;
- Serie A est exportee localement chez l'utilisateur et doit etre relancee apres alias Parma si le CSV est present ;
- Ligue 1 doit encore etre exportee et diagnostiquee manuellement ;
- CLV readiness confirme que les colonnes closing fiables restent le passage oblige ;
- `data/MATCHES.csv` doit etre inspecte en lecture seule pour savoir si des closing odds fiables existent ;
- `C_LTH/C_LTA` ne couvrent pas draw, totals ou BTTS ;
- une CLV partielle ne valide pas une strategie globale ;
- absence de validation humaine complete.

## Etat des modules

- `understat_probe.py` : export optionnel Understat local via soccerdata, chemins `Path`, dry-run sans reseau.
- `xg_dataset_quality.py` : controle lignes, saisons, completeness, xG coverage, doublons et fuite.
- `join_diagnostics.py` : join rate avant/apres alias, fuzzy suggestions, causes probables et join_quality.
- `team_name_normalizer.py` : alias manuels controles, dont La Liga, Bundesliga, Serie A et Ligue 1, sans modification des CSV source.
- `understat_xg_pipeline.py` : orchestration locale quality, jointure, rolling features, xG model et gouvernance optionnelle.
- `multi_league_xg_aggregator.py` : synthese Big 5 des rapports xG existants, sans recuperation reseau.
- `closing_odds_probe.py` : inspection lecture seule du CSV source pour colonnes closing H2H, total et BTTS, avec profil forensique des valeurs.
- `features_closing_enricher.py` : preview dans `reports/` pour joindre features actuelles et colonnes closing source, avec `clv_available/clv_reason`, sans ecrire dans `data/`.
- `clv_readiness_report.py` : inspection des colonnes closing manquantes, avec distinction calculable maintenant/apres enrichissement/dans preview, sans inventer de CLV.
- `clv_analysis.py` : CLV descriptive, accepte la preview partielle et exclut les lignes sans closing exacte.
- `calibration_report.py` : Brier, log loss, ECE, MCE et reliability curves.
- `statistical_validation.py` : IC ROI, bootstrap, Monte Carlo, drawdown, sample size et Benjamini-Hochberg.
- `decision_policy.py` : gates CLV/calibration/statistiques/multiple testing.
- `benchmark_governance.py` : registre enrichi V8.1 avec CLV, shadow report, ROI/drawdown shadow, nulls prudents et warnings si metriques absentes.
- `report_runner.py` : modes `--statistical`, `--shadow` et `--daily-shadow`.
- `dashboard_builder.py` : sections CLV, calibration, validation statistique, multiple testing, gouvernance finale et Shadow Mode Evidence.
- `shadow_ledger.py` : journal local des observations shadow dans `reports/`.
- `closing_manual_import.py` : import manuel de closing odds par `shadow_id`.
- `shadow_clv_report.py` : rapport CLV/ROI shadow, observation seulement.
- `daily_shadow_candidates.py` : preparation de candidats shadow depuis CSV live ou historique, sans recommandation de mise.
- `oracle_ops.py` : centre de controle local health/daily/full-local.
- `shadow_quality_audit.py` : controle colonnes, odds, CLV, doublons, dates, resultats et coverage.
- `evidence_gate.py` : statut de preuve `not_started`, `insufficient_evidence`, `blocked` ou `ready_for_deep_review`.
- `shadow_simulator.py` : ledgers synthetiques pour tester les workflows sans preuve reelle.
- `sample_size_planner.py` : estimation prudente des volumes necessaires.
- `shadow_message_formatter.py` : preview texte privee, sans API Telegram.

## Resultats connus

- 67 strategies/modeles ont ete evalues dans l'etat precedent.
- Meilleur score historique observe : 79/100.
- Candidats robustes : 0.
- Observations H2H favoris : watchlist seulement.
- xG EPL 2024-2025 : echantillon trop petit, pas de signal robuste.
- Ancien export Understat 1520 lignes : incomplet a cause d'une ambiguite de saison.
- Nouvel export Understat attendu 1900 lignes : base correcte pour un laboratoire EPL 2020-2025.
- EPL Understat 2020-2025 : jointure autour de 98%, quality exploitable, mais xG ne bat pas le marche.
- La Liga Understat 2020-2025 : export complet, jointure avant alias autour de 39.89%, apres alias autour de 99.89%, observation seulement.
- Bundesliga Understat 2020-2025 : export complet 1530 matchs, cinq saisons de 306 matchs, xG coverage 100%, jointure initiale autour de 24.12% avant alias et autour de 99.93% apres alias.
- Serie A Understat 2020-2025 : export utilisateur observe a 1900 matchs, cinq saisons completes, xG coverage 100%, jointure apres alias observee a 95.79% avant correction Parma ; `Parma Calcio 1913` est maintenant mappe vers `Parma`.
- Ligue 1 : aliases prets, export a lancer manuellement.
- CLV sur `data/features_modern.csv` est probablement indisponible tant que les colonnes closing `C_*` ne sont pas exportees.
- `data/MATCHES.csv` contient des colonnes `C_LTH/C_LTA` detectees par nom, mais V7.8 les a rejetees comme valeurs non plausibles pour des cotes decimales.
- Rien n'est branche aux picks Telegram ou Railway.

## Ce qui est valide

- Import historique massif local.
- Pricing no-vig descriptif.
- Backtest train/validation/test.
- Feature matrix locale reproductible.
- Exclusion par defaut des post-match features.
- Rolling features pre-match sans usage du match courant.
- Understat probe sans recuperation dans les tests.
- Quality gate Understat xG sans recuperation reseau.
- Diagnostic de jointure sans recuperation reseau.
- Pipeline xG local depuis CSV deja telecharge.
- Rapports locaux qui ne modifient pas `oracle_db.json`.
- Registre modele sans secrets, sans predictions individuelles et sans gros dataset.

## Ce qui reste invalide ou non confirme

- Transformer un ROI court terme en selection activee.
- Promouvoir un signal sans CLV positive.
- Promouvoir un signal si la correction multiple testing echoue.
- Promouvoir un signal si le bootstrap ROI p05 est inferieur ou egal a 0.
- Utiliser Kelly comme preuve d'edge.
- Considerer Telegram ou Railway comme etape de validation.
- Utiliser `home_xg` ou `away_xg` du match courant comme features predictives.
- Considerer `production_allowed` comme pari automatique.

## Prochaine vraie priorite

1. Commit/push la phase locale V8.3.
2. Lancer `oracle_ops.py --health` puis `oracle_ops.py --odds-lab`.
3. Remplir `reports/manual_odds_snapshot_template.csv` avec quelques cotes reelles.
4. Importer dans `reports/odds_snapshots.csv`.
5. Convertir en observations shadow en dry-run, puis appliquer seulement si les lignes sont propres.
6. Capturer des snapshots near-close fiables.
7. Matcher les near-close vers le ledger avec `odds_closing_matcher.py --dry-run`.
8. Lire `shadow_quality_audit.py`, `shadow_clv_report.py` et `evidence_gate.py`.
9. Continuer jusqu'a sample significatif et chercher une source closing complete fiable.

## V8.3 Odds Source Adapter Lab

V8.3 prepare la collecte de cotes propre sans activer de reseau :

- configuration odds dans `config/odds_sources.example.json` ;
- aucune vraie cle commitee ;
- import manuel CSV ;
- adaptateurs API-Football et The Odds API en dry-run/fixture ;
- snapshot store local dans `reports/` ;
- conversion snapshots vers observations shadow ;
- matching near-close vers closing odds du ledger ;
- rapport qualite sources de cotes ;
- integration `oracle_ops.py --odds-lab` et `report_runner.py --odds-lab`.

Le blocage central reste inchange : sans CLV fiable, sans sample suffisant et sans validation historique/live, aucun signal robuste n'est active.

## V8.4 Odds Lab Usability

V8.4 rend la collecte manuelle praticable :

- wizard CLI `odds_lab_wizard.py` ;
- validation manuelle stricte et fichiers de rejets ;
- store snapshots validable et filtrable ;
- conversion taken-only par defaut vers shadow ;
- matching near-close plus prudent ;
- audit intake odds ;
- demo end-to-end synthetique.

Le statut reste laboratoire local. Les snapshots ne deviennent une preuve que si les cotes sont reelles, horodatees, matchables et accumulees sur un sample significatif.

## V8.7 Matchday Runner Dry-Run Staging

V8.7 corrige le workflow reel observe pendant les tests de juin :

- `matchday_runner.py --full-dry-run` cree un store et un ledger temporaires ;
- une taken odds valide peut maintenant simuler une observation shadow meme si le store reel est vide ;
- `--phase pre_match` ne bloque pas l'absence normale de near-close ;
- `--phase near_close` exige taken + near-close ;
- `--phase post_match` exige taken + near-close + resultats ;
- `matchday_status_report.py` lit un pack et produit `phase_detected`, warnings, blockers et prochaines actions ;
- `evidence_gate.py`, `real_observation_guard.py`, `odds_lab_wizard.py`, `oracle_ops.py`, `report_runner.py` et `dashboard_builder.py` lisent la phase.

Le statut reste non valide pour toute conclusion de performance. La phase aide seulement a savoir quoi collecter ensuite.

## V8.8 Soccer Odds API Automation & Near-Close Guardrails

V8.8 rend la collecte The Odds API praticable sans automatisme reseau :

- `soccer_odds_sport_scanner.py` scanne les sport keys soccer en dry-run ;
- `the_odds_api_adapter.py` supporte `--near-close`, filtres bookmaker/date, `--max-events`, `--one-side-per-event` et `--raw-dump` hors `data/` ;
- `odds_shadow_selector.py` choisit une selection limitee depuis les snapshots ;
- `odds_to_shadow.py` accepte `--selection-csv` pour ne convertir que les observations choisies ;
- `odds_closing_matcher.py` ajoute filtres event/ligue/date/bookmaker, `--only-shadow-pending` et preference latest-before-kickoff ;
- `near_close_workflow.py` affiche les observations en attente de closing et les commandes near-close ;
- `api_odds_collection_runner.py` orchestre scan/collect/select/to-shadow en dry-run ;
- `oracle_ops.py --api-odds-status`, `--near-close-status`, `--near-close-next`, `--real-guard-ledger` et `report_runner.py --api-odds` exposent le workflow.

Le reseau reste impossible sans `--allow-network`. Le guard recommande `--scope ledger` pour les runs reels afin que le store de snapshots complet ne bloque pas des lignes non selectionnees. Statut final inchange : observation shadow seulement, preuve insuffisante sans CLV reelle et sample significatif.

## V8.9 Autonomous Odds Operations

V8.9 aide a terminer le cycle de vie des observations deja creees :

- `event_lifecycle_manager.py` calcule les statuts `pre_match_waiting_close`, `near_close_due_soon`, `near_close_overdue`, `waiting_result`, `result_overdue`, `complete` ;
- `near_close_scheduler.py` genere les commandes near-close par ligue ;
- `result_capture_helper.py` cree et valide `manual_results_due.csv` ;
- `shadow_progress_dashboard.py` expose pending closing, pending results, CLV coverage, ROI coverage et sample progress ;
- `odds_autopilot_dryrun.py` propose quoi faire maintenant sans reseau ;
- `evidence_gate.py --lifecycle` ajoute les warnings/blockers lifecycle ;
- `report_runner.py --shadow-ops` produit la vue locale complete.

Protection ajoutee : `api_odds_collection_runner.py --apply` peut refuser si trop d'observations sont sans closing. La priorite reste la capture near-close et les resultats manuels, pas l'ajout massif de nouvelles lignes.
