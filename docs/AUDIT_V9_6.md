# Audit V9.6 vers V10

Date d'audit local : 2026-07-18.

Ce document audite l'etat observe du depot local avant la migration additive V10. Le depot reel est `oracle-bot-`, avec son propre `.git`. Le dossier parent contient aussi un depot Git, mais le projet operationnel est celui du sous-dossier.

## Architecture existante

- Point d'entree Railway/Telegram historique : `main.py`, qui appelle `bot_app_v52.main`.
- Configuration historique : `config.py`, avec `TELEGRAM_TOKEN`, `CHAT_ID`, `ODDSPAPI_KEY`, `ODDS_API_KEY`, `THE_ODDS_API_KEY`, `FOOTBALL_KEY`, `API_FOOTBALL_KEY`, `APISPORTS_KEY`, `FOOTBALL_DATA_KEY` et `DATABASE_URL` via `persistent_memory.py`.
- Orchestration laboratoire : `oracle_ops.py`, `report_runner.py`, `daily_operations_runner.py`, `matchday_runner.py`.
- Pricing et evaluation : `pricing.py`, `model_trainer.py`, `backtest_evaluator.py`, `calibration_report.py`, `statistical_validation.py`.
- Donnees et features : `feature_builder.py`, `xgabora_dataset_import.py`, `external_xg_features.py`, `understat_xg_pipeline.py`.
- Odds/API : adaptateurs API-Football, The Odds API, odds snapshots, near-close, result capture.
- Shadow ledger : `shadow_ledger.py`, `shadow_clv_report.py`, `shadow_result_matcher.py`.
- Telegram read-only : `telegram_config.py`, `telegram_notifier.py`, `telegram_shadow_publisher.py`, `telegram_near_close_reporter.py`, `telegram_result_reporter.py`.
- LLM : contrat et preview seulement via `llm_analyst_contract.py` et `agent_orchestrator_dryrun.py`; pas d'orchestration LLM production observee.

## Composants fonctionnels

- Les scripts API-Football et The Odds API refusent le reseau par defaut et exigent des flags explicites.
- Telegram est read-only par defaut et l'envoi reel exige `--allow-send`.
- Les rapports CLV, proof dashboard et evidence gate existent.
- V9.8 est deja presente dans l'arbre de travail : settlement shadow result, completed cycle et Telegram result reporter.
- `.gitignore` ignore `data/`, `reports/`, `external_data/`, `variable/`, `.env` et les gros `oracle_db*.json`.
- `python -m compileall -q .` est passe pendant l'audit.

## Composants incomplets

- Pas de schema PostgreSQL normalise V10, pas de SQLAlchemy/Alembic observe.
- `persistent_memory.py` stocke une memoire JSON unique dans PostgreSQL si `DATABASE_URL` existe.
- Pas de CLI Typer ni package `src/app`; le depot est encore essentiellement flat.
- Pas de Pydantic installe localement au moment de l'audit.
- Pas de workflows GitHub observes avant la migration V10.
- Pas de moteur agents LLM production avec Responses API, budgets, schemas persistants et traces de cout.
- Pas de backtest V10 complet avec ablation agents/judge.

## Dettes techniques

- Plusieurs gros dumps locaux existent hors Git et ne doivent jamais etre trackes.
- Les noms d'environnement Telegram historiques (`TELEGRAM_TOKEN`, `CHAT_ID`) coexistent avec les noms read-only recents (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`).
- Beaucoup de tests sont des scripts plats `test_*.py`, pas encore organises en pyramide `tests/unit`, `tests/integration`, etc.
- `project_audit.py` est complet mais long : un lancement initial sans fenetre longue a depasse 124 secondes.

## Bugs ou risques observes

- Aucun secret n'a ete affiche. Les recherches ont porte uniquement sur les noms de variables.
- Les chiffres historiques 284 matchs, 28 514 cotes, 507 H2H et 5 selections viennent du contexte utilisateur; aucun hardcode exact de ces volumes n'a ete trouve dans les fichiers trackes recherches. Les artefacts `reports/` sont ignores par Git et peuvent contenir les sorties de run.
- Le Dockerfile copie tout le contexte; une `.dockerignore` est necessaire pour eviter les dumps locaux.

## Securite et secrets

- `.gitignore` bloque les donnees, reports, env locaux et dumps.
- Les exemples de configuration Telegram sont vides ou factices.
- Les modules Telegram masquent le token dans les logs.
- La migration V10 ajoute `.env.example`, `.dockerignore`, un secret scan local et un workflow CI offline.

## Dry-run et scans

- Les runners API utilisent `--allow-network` pour tout appel externe.
- Les chemins ledger restent dry-run par defaut et exigent `--apply` pour ecrire.
- Telegram exige `--allow-send` pour un envoi reel.
- `oracle_ops.py` expose les commandes de laboratoire avec `lab_only=true` et `can_influence_picks=false`.

## Ecart V9.6 vers V10

- V9.x est un laboratoire robuste de collecte, shadow ledger, CLV et Telegram read-only.
- V10 cible une architecture hybride : data/ledger/modeles deterministes d'abord, agents LLM seulement apres filtrage, juge final incapable d'inventer des donnees.
- Les manques principaux sont la persistance relationnelle, le moteur statistique multi-modeles versionne, l'orchestration agents stricte, le backtest walk-forward complet et l'API interne.

## Strategie de migration progressive

1. Conserver `main.py`, le Dockerfile et les datasets intacts.
2. Ajouter une couche additive `v10/` avec primitives testees : odds, EV, CLV, data quality, candidates, risk paper-only, settlement, contrats agents, demo offline.
3. Brancher `project_audit.py` sur cette couche sans casser les tests V9.x.
4. Documenter architecture, securite, evaluation, prompts et runbook.
5. Migrer ensuite la persistance vers PostgreSQL normalise avec migrations, sans remplacer brutalement `persistent_memory.py`.
6. Ajouter fournisseurs/replay, modeles statistiques, agents LLM mock puis production avec budgets.

## Validations apres premiere migration V10

- `python -m compileall -q .` : OK.
- Suite large `test_*.py` : 118/118 OK.
- `python project_audit.py` : OK local prudent, sans warning ni erreur bloquante.
- `python scripts/secret_scan.py --root .` : 0 fichier problematique.
- `python app.py doctor` : OK, secrets seulement en presence booleenne.
- `python app.py demo end-to-end` : OK, `WATCH`, `network_used=false`, `telegram_sent=false`.
- Docker local non execute : la commande `docker` n'est pas disponible dans cet environnement.

Le timeout initial de `project_audit.py` venait du scan textuel de gros dumps locaux. L'audit ignore maintenant les artefacts volumineux et les dossiers deja exclus par `.gitignore`.
