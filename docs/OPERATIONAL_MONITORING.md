# Operational Monitoring

La Phase 5 cree des alertes en base, pas d'envoi Telegram.

Surveillances:

- scheduler silencieux;
- jobs bloques;
- leases expires;
- provider degrade;
- quotas faibles;
- resultats non regles;
- budget LLM epuise;
- migrations non appliquees.

Endpoints:

- `GET /health/live`
- `GET /health/ready`
- `GET /health/deep`
- `GET /metrics`
- `GET /dashboard`

Les endpoints detailles sont read-only et proteges par `INTERNAL_API_TOKEN` en environnement non local.

