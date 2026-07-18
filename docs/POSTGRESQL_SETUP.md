# PostgreSQL V10

Cette phase ajoute une couche relationnelle V10 additive. Elle ne migre pas les donnees V9 automatiquement et ne modifie pas `oracle_db*.json`, `data/`, `reports/` ou `external_data/`.

## Variables

Noms attendus :

- `DATABASE_URL`
- `DATABASE_ECHO`
- `DATABASE_POOL_SIZE`
- `DATABASE_MAX_OVERFLOW`
- `DATABASE_POOL_TIMEOUT_SECONDS`
- `DATABASE_STATEMENT_TIMEOUT_MS`
- `APP_ENV`
- `LOG_LEVEL`
- `DRY_RUN`
- `PAPER_BETTING_ENABLED`
- `REAL_MONEY_ACTIONS_ENABLED`

`REAL_MONEY_ACTIONS_ENABLED=true` est refuse par la configuration V10. Cette phase ne contient aucune integration bookmaker.

## Installation locale

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL="postgresql+psycopg://oracle:oracle@localhost:5432/oracle_v10"
python app.py config validate
python app.py db upgrade
python app.py db status
python app.py db doctor
```

`postgresql://` est converti en `postgresql+psycopg://` cote SQLAlchemy.

## Alembic

Commandes directes :

```powershell
alembic upgrade head
alembic current
alembic history
```

Commandes CLI equivalentes :

```powershell
python app.py db upgrade
python app.py db status
```

## Railway

Railway fournit normalement `DATABASE_URL`. Ne suppose pas que le filesystem Railway est persistant : les payloads bruts, snapshots et runs doivent etre en PostgreSQL.

Points d'exploitation :

- activer PostgreSQL dans Railway ;
- definir `DATABASE_URL` avec la valeur Railway ;
- definir les secrets provider/Telegram/OpenAI uniquement dans les variables Railway ;
- lancer `python app.py db upgrade` une seule fois par deploiement ;
- garder `DRY_RUN=true` et `REAL_MONEY_ACTIONS_ENABLED=false` ;
- utiliser `python app.py db doctor` comme smoke check base ;
- surveiller la taille de `v10_raw_api_payloads` et definir une retention future avant gros volumes.

## Pool et SSL

La configuration V10 expose :

- `DATABASE_POOL_SIZE`
- `DATABASE_MAX_OVERFLOW`
- `DATABASE_POOL_TIMEOUT_SECONDS`
- `DATABASE_STATEMENT_TIMEOUT_MS`

Pour Railway, commencer petit. Le timeout statement est applique via options PostgreSQL quand le dialecte est PostgreSQL.

## Limite de validation locale

SQLite est autorise uniquement pour les tests rapides et la demo offline. Il ne valide pas les verrous advisory PostgreSQL natifs, le comportement JSONB exact, ni les contraintes concurrentes production.
