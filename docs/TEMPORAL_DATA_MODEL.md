# Modele Temporel V10

La regle centrale de V10 est simple : une decision future doit pouvoir etre rejouee avec uniquement les donnees observees avant son heure de decision.

## Conventions

- `event_time` : moment reel du match ;
- `observed_at` : moment ou Oracle observe l'information ;
- `effective_at` : moment a partir duquel l'information est applicable ;
- `created_at` : creation technique en base ;
- `updated_at` : derniere modification technique.

Toutes les dates metier sont timezone-aware et normalisees en UTC. Les dates naïves sont refusees a l'ecriture par le type `UTCDateTime`.

## Odds snapshots

`v10_odds_snapshots` est append-only pour l'historique de cotes :

- un nouveau `observed_at` peut produire une nouvelle ligne ;
- une cote modifiee produit une nouvelle ligne ;
- un doublon strict est ignore via `content_fingerprint` ;
- les anciennes lignes ne sont pas ecrasees.

## Requetes anti-fuite

Repositories disponibles :

- `get_fixture_state_as_of(fixture_id, as_of)`
- `get_latest_odds_as_of(fixture_id, market, as_of)`
- `get_market_snapshot_as_of(fixture_id, market, as_of)`
- `get_raw_payloads_observed_before(as_of)`

Une requete `as_of` ne doit jamais retourner une observation posterieure.

## Exemple

```powershell
python app.py odds latest --fixture-id <uuid> --as-of 2026-06-01T10:30:00+00:00
python app.py odds history --fixture-id <uuid>
python app.py quality fixture --fixture-id <uuid>
```

## SQLite et PostgreSQL

SQLite est utilise par les tests offline pour valider la logique deterministe. PostgreSQL reste la cible production : JSONB, pooling, locks advisory natifs et contraintes concurrentes doivent etre valides sur PostgreSQL avant exploitation.
