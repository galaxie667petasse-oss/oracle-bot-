# Format Odds Snapshot Oracle

Chaque snapshot normalise utilise les colonnes suivantes :

```text
snapshot_id,captured_at,source,source_event_id,league,match_date,kickoff_time,home_team,away_team,bookmaker,market_type,side,odds,odds_format,is_live,is_near_close,raw_market,raw_side,raw_payload_ref,normalized_home,normalized_away,validation_status,validation_reason
```

## Marches

- `h2h`
- `draw`
- `total`
- `btts`
- `handicap`
- `unknown`

## Sides

- `home`
- `away`
- `draw`
- `over`
- `under`
- `yes`
- `no`
- `unknown`

## Validation

Une cote est acceptee seulement si elle est decimale, strictement superieure a `1.01` et inferieure a `100`.

Les valeurs entre `0` et `1` sont rejetees comme probabilites probables. Le pipeline ne convertit jamais une probabilite en cote sans champ explicitement documente.

## Utilisation

```bash
python manual_odds_import.py --input reports/manual_odds_snapshot.csv --store reports/odds_snapshots.csv
python odds_snapshot_store.py --summary
python odds_to_shadow.py --snapshots reports/odds_snapshots.csv --ledger reports/shadow_ledger.csv --dry-run
python odds_closing_matcher.py --ledger reports/shadow_ledger.csv --snapshots reports/odds_snapshots.csv --dry-run
```

Le format sert au laboratoire de preuve. Il ne cree aucune mise.

## Controle V8.4

Valider le store :

```bash
python odds_snapshot_store.py --validate
```

Exporter seulement le near-close :

```bash
python odds_snapshot_store.py --near-close-only --output reports/odds_near_close.csv
```

Filtrer un marche :

```bash
python odds_snapshot_store.py --filter --market h2h --output reports/odds_h2h.csv
```
