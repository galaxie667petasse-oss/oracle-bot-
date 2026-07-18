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
