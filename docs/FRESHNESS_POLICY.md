# Freshness Policy

Version: `prematch_freshness_v1`.

Parametres par defaut:

- `MAX_FIXTURE_AGE_MINUTES=30`
- `MAX_ODDS_AGE_MINUTES_T24=180`
- `MAX_ODDS_AGE_MINUTES_T90=20`
- `MAX_ODDS_AGE_MINUTES_T30=10`
- `MAX_ODDS_AGE_MINUTES_T10=5`
- `MAX_LINEUP_AGE_MINUTES=15`
- `MAX_AVAILABILITY_AGE_MINUTES=180`
- `MAX_TEAM_STATS_AGE_HOURS=24`
- `MAX_STANDINGS_AGE_HOURS=24`

Une cote perimee bloque le candidat. Les lineups et availability sont conditionnels si aucun provider structure n'est disponible.

