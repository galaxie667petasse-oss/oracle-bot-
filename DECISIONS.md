# Decisions V10

## ADR-001 - Migration additive

Decision : ajouter `v10/` sans modifier `main.py`.

Raison : le V9.x contient beaucoup de garde-fous utiles et doit rester executable.

## ADR-002 - Calculs deterministes avant LLM

Decision : odds, EV, CLV, data quality, candidates, risk et settlement sont calcules en Python.

Raison : le LLM explique et critique, mais ne doit jamais devenir source de verite.

## ADR-003 - Paper betting uniquement

Decision : `REAL_MONEY_ACTIONS_ENABLED=false` par defaut et action bookmaker non supportee.

Raison : le projet reste laboratoire local, sans mise reelle ni promesse de rentabilite.

## ADR-004 - Replay/offline first

Decision : la demo V10 fonctionne sans cle, sans reseau et sans Telegram reel.

Raison : les tests et CI ne doivent jamais dependre d'un fournisseur payant.

## ADR-005 - PostgreSQL plus tard, pas de big bang

Decision : ne pas remplacer `persistent_memory.py` dans la premiere passe V10.

Raison : la migration vers schema relationnel demande migrations, repositories et tests dedies.

## ADR-006 - PostgreSQL V10 additif

Decision : creer un schema `v10_*` via SQLAlchemy 2 et Alembic sans modifier les tables ou fichiers V9.

Raison : la persistance relationnelle doit devenir rejouable et auditable, mais le bot historique doit rester executable.

## ADR-007 - Snapshots de cotes append-only

Decision : `v10_odds_snapshots` n'ecrase jamais une cote observee. Le fingerprint inclut fixture, bookmaker, marche, selection, ligne, cote et `observed_at`.

Raison : la future decision doit pouvoir etre rejouee sans fuite de cote observee apres l'heure de decision.

## ADR-008 - SQLite seulement pour tests offline

Decision : autoriser SQLite pour migrations et demo locales, mais documenter que PostgreSQL reste la cible production.

Raison : l'environnement local peut ne pas avoir PostgreSQL ; SQLite valide la logique deterministe mais pas les garanties concurrentes production.

## ADR-009 - Moteur statistique sans LLM

Decision : les probabilites V10 sont produites par `v10/statistics` avec Elo, Poisson, Dixon-Coles experimental, calibration et ensemble. Les agents LLM futurs ne pourront pas recalculer ou ajuster librement ces probabilites.

Raison : les faits numeriques doivent rester reproductibles, testables et auditables.

## ADR-010 - Features temporelles explicites

Decision : tout dataset ou prediction statistique doit recevoir un `TemporalContext` ou un `as_of` explicite. Le builder traite l'historique avant la periode cible pour calculer les features, puis ne produit des lignes que dans la fenetre demandee.

Raison : une decision future doit pouvoir etre rejouee avec uniquement les donnees observees avant son heure de decision.

## ADR-011 - Dixon-Coles experimental

Decision : `dixon_coles_v1` est disponible mais marque experimental. Il corrige les scores faibles via `tau`, utilise une recherche contrainte de `rho` et ne doit pas etre considere meilleur que Poisson sans validation hors echantillon.

Raison : le modele est utile pour diagnostic et comparaison, mais un petit echantillon peut rendre l'optimisation instable.

## ADR-012 - LLM shadow orchestration fail-closed

Decision : la Phase 4 ajoute Luna/Terra/Sol comme tiers logiques configurables, mais garde `LLM_ENABLED=false`, `LLM_ALLOW_PAID_CALLS=false` et budgets a zero par defaut.

Raison : une cle OpenAI seule ne doit jamais declencher un cout ou une decision.

## ADR-013 - 12 roles logiques, pas 12 appels par defaut

Decision : les roles compatibles sont regroupes en panels Terra. Devil's Advocate reste separe et Sol reste rare.

Raison : le cout est controle sans supprimer l'independance critique la plus importante.

## ADR-014 - Evidence policy et gate deterministe souverain

Decision : chaque affirmation LLM doit referencer une preuve typee valide as_of. Le gate deterministe peut toujours annuler une acceptation Sol.

Raison : un JSON valide mais semantiquement faux doit devenir un hard veto.
