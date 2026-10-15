# Railway Deployment Preparation

Aucun deploiement n'est lance par defaut. `RAILWAY_ALLOW_DEPLOY=false`.

## Option minimale recommandee

- PostgreSQL Railway.
- Service web leger:

```powershell
uvicorn v10.api:app --host 0.0.0.0 --port $env:PORT
```

- Pre-deploy:

```powershell
alembic upgrade head
```

- Healthcheck: `/health/ready`.
- Cron dispatcher UTC toutes les cinq minutes:

```powershell
python app.py scheduler tick --max-runtime-seconds 240 --max-jobs 50
```

## Notes

- Le filesystem Railway n'est pas considere persistant.
- Les etats importants vont en PostgreSQL.
- Pas de Redis dans cette phase.
- Le scheduler doit quitter apres chaque tick.
- Les secrets sont fournis par variables Railway et jamais commites.

