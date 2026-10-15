# ORACLE : carte du projet vérifiée le 15 octobre 2026

État actualisé par la mission 2 : [publication, CI réelle et limites](docs/V11_MISSION2.md).

## Identité et conservation

- Dépôt distant : `galaxie667petasse-oss/oracle-bot-`.
- Checkout V11 : `oracle-v11`.
- Branche : `codex/oracle-v11-safe-integration`, base `e565b2438269561f40970c5debe3a13be05facf7`.
- CI de cette base : [38776566962, success](https://github.com/galaxie667petasse-oss/oracle-bot-/actions/runs/38776566962), SHA confirmé via API GitHub.
- Branche historique distante : `backup/oracle-v10-before-v11-20261015`, `e0446ba2aa2fc1ab29c1a1b5e170593decb7eb41`.
- Ancien checkout `..\oracle-bot-` : branche `codex/v10-hybrid-engine`, au même SHA historique, avec des modifications Phase 4 non commitées. Elles restent dans ce checkout ; aucun transfert ni changement de branche.
- Le `.git` du dossier parent `IA BOT` est un dépôt sans commit, distinct des deux dépôts imbriqués.

## Architecture effective

| Domaine | Composants conservés | Intégration V11 |
|---|---|---|
| Entrées historiques | `app.py`, `main.py`, `bot_app.py`, scripts à la racine | `python -m v11`, sans modifier les commandes historiques |
| Fournisseurs | `api_football_*_adapter.py`, `the_odds_api_adapter.py`, `v10/normalization/` | `v11/sources.py` réutilise les normaliseurs fixtures/odds, collecte bornée, clés FR explicites |
| Cache, quotas, verrous | `v10/operations/provider_cache.py`, `quota.py`, `v10/db/locks.py` | réutilisés dans une base de cache V10 séparée, migration Alembic existante |
| Statistiques | `v10/statistics/{poisson,dixon_coles,elo,markets,training,calibration,backtest}.py` | V10 inchangé, `v11/models.py` adapte les trois modèles penaltyblog |
| Marché sans marge | `v10/odds.py` | baseline 1N2 par bookmaker/source, sans mélanger les meilleurs prix |
| Règlement | `v10/settlement.py`, `settlement.py` | `v11/markets.py` : temps réglementaire explicite, scores exacts, lignes asiatiques et demi-règlements |
| Historique | ledger CSV/JSON historique, `v10/db/models.py`, repositories SQLAlchemy | `v11/ledger.py` : projection SQLite isolée, snapshots et prédictions immuables, événements résultats séparés |
| Validation | `v10/statistics/metrics.py`, tests historiques | `v11/evaluation.py` : folds chronologiques, embargo, calibration séparée, comparaison appariée au marché |
| Simulation | outils shadow historiques | `v11/paper.py` : politique hypothétique fixée, ROI et CLV conditionnels, aucune exécution |
| Web | `v10/api.py`, endpoints `/api/v10/*` et dashboard V10 | route `/v11`, API `/api/v11/*`, token obligatoire pour toutes les données V11 |
| Agents/LLM | `v10/agents.py`, `v10/llm/`, `prompts/` | conservés, aucun appel LLM dans le parcours V11 |
| Opérations | `v10/operations/`, scheduler, Telegram historique | conservés, aucune publication ni planification créée par V11 |
| Expérimentations | `external_adapters/`, `external_xg_*`, `xg_model_lab.py`, `model_registry.json` | conservées, aucune promotion ni fusion avec V11 |

Le nouveau ledger n'est pas un remplacement des tables V10 : il stocke les analyses V11 sans toucher aux migrations historiques ni aux bases persistantes existantes. La base de cache séparée réutilise réellement le schéma, les migrations et les services V10. Aucun `DATABASE_URL` de production n'est utilisé par la commande V11 de collecte.

## Parcours V11 et frontières

1. Collecte explicite, bornée à une requête par commande, ou import d'un `Snapshot` validé.
2. Une photographie contient fixtures, cotes et historique de résultats avec dates de disponibilité explicites.
3. Analyse de la date UTC : historique de la même compétition, disponible avant la décision ; frais et pré-match uniquement.
4. Modèles V10 et penaltyblog via la CLI ou la case dédiée du web ; aucune combinaison promue automatiquement.
5. Règlements/EV calculés depuis la grille ; pas d'intervalle de confiance individuel fabriqué.
6. Scellement de la prédiction avec source, version, hash d'entraînement et snapshot d'origine.
7. Ajout ultérieur d'événements résultats ; aucune modification de la prédiction.
8. Consultation authentifiée depuis le web, simulation et validation depuis la CLI.

Toutes les décisions restent `ABSTAIN`, `can_influence_picks=false`. Les valeurs affichées sont de la recherche, pas des recommandations validées. `synthetic`, `manual` et `real_provider` restent distingués ; la simulation refuse de les agréger.

## Dépendances et validation

- Socle : `requirements.txt`, CI Python 3.12, FastAPI, SQLAlchemy, Alembic, Pydantic, httpx ; dépendances V10 conservées.
- Extension optionnelle : `requirements-v11.txt`, penaltyblog 1.6.2 ; version réellement installée et testée, pas une API simulée. La version est conservée dans les diagnostics. `requirements-v11-windows-py312.lock.txt` enregistre les versions exactes de l'environnement Python 3.12 isolé validé.
- Tests V11 : `tests/test_v11.py` ; tests numériques, temporels, cache/quota, rejet des sorties invalides, restauration, API et bibliothèque réelle.
- Tests V10 : cinq `test_v10_*.py`, plus 122 scripts `test_*.py` historiques.
- Contrôles : `scripts/secret_scan.py`, `project_audit.py`, `compileall`, `git diff --check`.
- CI additive : job `v11` dans `.github/workflows/ci.yml`. Docker historique conservé ; `Dockerfile.v11` prépare un service web non root.
- Mission 2 : `v11.api:app` sert uniquement V11 ; `v10.api:app` conserve les routes historiques. `compose.v11.yml` prépare un accès loopback, un volume nommé et un système de fichiers restreint. Les assets web externes permettent une CSP sans `unsafe-inline`.
- `v11/results.py` applique les résultats FT via un mapping explicite fixture/équipes/kickoff, sans réécriture des prédictions. `evaluate --quotes-file` rend les comparaisons de marché accessibles par CLI.
- Les dépendances exactes sont dans `requirements-v11-py312.lock.txt`, exécutées sous Linux en CI ; le lock Windows antérieur est conservé.
- Preuves détaillées et limites : `docs/V11_VALIDATION.md`. Usage : `docs/V11_RUNBOOK.md`.

## Données et restauration

Sauvegarde locale hors des dépôts : `..\oracle-v11-backup-20261015`.

- `v10-all-refs.bundle` et `v11-start.bundle` : `git bundle verify` réussi, historique complet pour les références présentes.
- `local-state.zip` : 1 930 fichiers, 575 963 761 octets compressés, CRC vérifié. Comprend les modifications locales et les répertoires de données ; caches/environnements exclus.
- `manifest.json` : chemins, tailles et SHA-256 des fichiers sources.
- Les fichiers SQLite ont été copiés via l'API de sauvegarde SQLite et contrôlés par `PRAGMA integrity_check`.
- Restauration du code : cloner le bundle dans **un nouveau dossier**, extraire l'archive dans **un autre nouveau dossier**, comparer au manifeste avant toute fusion.
- Restauration V11 : `python -m v11 --ledger SOURCE backup NOUVELLE_COPIE`, puis `status`. Triggers UPDATE/DELETE, clés étrangères et hashes vérifiés par les tests.

Ces sauvegardes restent sur le même ordinateur : elles ne constituent pas une sauvegarde hors machine. Aucun upload de données ou de secrets n'a été effectué.

## Sources documentaires consultées

- [penaltyblog : modèles et API](https://penaltyblog.readthedocs.io/en/latest/models/overview.html) ; les signatures et comportements utilisés ont ensuite été inspectés dans la version 1.6.2 installée.
- [The Odds API : bookmakers](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html) : clés FR documentées `betclic_fr`, `winamax_fr`, `unibet_fr`, `pmu_fr`, `netbet_fr` ; la liste documentaire ne prouve pas leur présence dans une réponse réelle.
- [The Odds API v4](https://the-odds-api.com/liveapi/guides/v4/) : sélection explicite des bookmakers, coût par marchés et groupes de dix bookmakers, headers de quotas.
- [API-Football v3](https://www.api-football.com/documentation-v3) ; pas de vérification live faute de clé.
