import argparse
import csv
import html
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from odds_normalizer import normalize_odds_rows, write_normalized_csv
from odds_source_config import get_api_key_from_env, load_odds_source_config, validate_config
from api_football_fixtures_adapter import fetch_fixtures, normalize_fixtures_payload, read_fixture as read_fixtures_fixture


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties API-Football odds doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _fixture_rows(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in payload.get("response") or []:
        fixture = item.get("fixture") or {}
        league = item.get("league") or {}
        teams = item.get("teams") or {}
        home = (teams.get("home") or {}).get("name") or item.get("home_team") or ""
        away = (teams.get("away") or {}).get("name") or item.get("away_team") or ""
        kickoff = str(fixture.get("date") or "")
        match_date = kickoff[:10] if kickoff else str(item.get("match_date") or "")
        for bookmaker in item.get("bookmakers") or []:
            bookmaker_name = bookmaker.get("name") or bookmaker.get("title") or ""
            for bet in bookmaker.get("bets") or []:
                raw_market = bet.get("name") or bet.get("label") or ""
                for value in bet.get("values") or []:
                    raw_side = value.get("value") or value.get("label") or value.get("name") or ""
                    rows.append({
                        "captured_at": item.get("captured_at") or "",
                        "source": "api_football",
                        "source_event_id": fixture.get("id") or item.get("fixture_id") or "",
                        "league": league.get("name") or item.get("league") or "",
                        "match_date": match_date,
                        "kickoff_time": kickoff,
                        "home_team": home,
                        "away_team": away,
                        "bookmaker": bookmaker_name,
                        "market_type": raw_market,
                        "side": raw_side,
                        "odds": value.get("odd") or value.get("odds") or value.get("price") or "",
                        "is_live": item.get("is_live") or "",
                        "is_near_close": item.get("is_near_close") or "",
                        "raw_market": raw_market,
                        "raw_side": raw_side,
                        "raw_payload_ref": str(fixture.get("id") or ""),
                    })
    return rows


def _load_fixture_csv(path: str) -> List[Dict[str, Any]]:
    if not path or not Path(path).exists():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        return [dict(row) for row in csv.DictReader(fh)]


def _fixture_index(fixtures: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in fixtures:
        fixture_id = str(row.get("fixture_id") or row.get("source_event_id") or row.get("id") or "").strip()
        if not fixture_id:
            continue
        index[fixture_id] = {
            "fixture_id": fixture_id,
            "league": row.get("league") or row.get("league_name") or "",
            "country": row.get("country") or "",
            "match_date": row.get("date") or row.get("match_date") or "",
            "kickoff_time": row.get("kickoff_time") or row.get("date") or "",
            "home_team": row.get("home_team") or row.get("home") or "",
            "away_team": row.get("away_team") or row.get("away") or "",
            "status": row.get("status") or "",
            "normalized_home": row.get("normalized_home") or "",
            "normalized_away": row.get("normalized_away") or "",
        }
    return index


def load_fixture_index(fixtures_csv: str = "", fixtures_json: str = "") -> Dict[str, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    rows.extend(_load_fixture_csv(fixtures_csv))
    if fixtures_json and Path(fixtures_json).exists():
        payload = read_fixtures_fixture(fixtures_json)
        rows.extend(normalize_fixtures_payload(payload))
    return _fixture_index(rows)


def enrich_raw_rows_with_fixtures(rows: List[Dict[str, Any]], fixtures: Dict[str, Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    enriched = 0
    out: List[Dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        fixture_id = str(payload.get("source_event_id") or payload.get("raw_payload_ref") or "").strip()
        fixture = fixtures.get(fixture_id)
        if fixture:
            before_teams = bool(payload.get("home_team") and payload.get("away_team"))
            payload["home_team"] = payload.get("home_team") or fixture.get("home_team") or ""
            payload["away_team"] = payload.get("away_team") or fixture.get("away_team") or ""
            payload["league"] = payload.get("league") or fixture.get("league") or ""
            payload["match_date"] = payload.get("match_date") or fixture.get("match_date") or str(fixture.get("kickoff_time") or "")[:10]
            payload["kickoff_time"] = payload.get("kickoff_time") or fixture.get("kickoff_time") or ""
            payload["raw_payload_ref"] = ";".join([
                f"fixture_id={fixture_id}",
                f"country={fixture.get('country') or ''}",
                f"status={fixture.get('status') or ''}",
            ])
            if not before_teams and payload.get("home_team") and payload.get("away_team"):
                enriched += 1
        out.append(payload)
    return out, enriched


def normalize_api_football_payload(payload: Dict[str, Any], fixture_index: Dict[str, Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
    raw_rows = _fixture_rows(payload)
    if fixture_index:
        raw_rows, _ = enrich_raw_rows_with_fixtures(raw_rows, fixture_index)
    return normalize_odds_rows(raw_rows, source="api_football")


def read_fixture(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_api_football_odds(
    config: Dict[str, Any],
    date: str = "",
    fixture_id: str = "",
    league_id: str = "",
    season: str = "",
    bookmaker: str = "",
    market: str = "",
) -> Dict[str, Any]:
    source = config.get("api_football") or {}
    key = get_api_key_from_env("api_football", config)
    if not key:
        raise ValueError("Cle API-Football absente dans l'environnement.")
    base_url = str(source.get("base_url") or "https://v3.football.api-sports.io").rstrip("/")
    params = {}
    if date:
        params["date"] = date
    if fixture_id:
        params["fixture"] = fixture_id
    if league_id:
        params["league"] = league_id
    if season:
        params["season"] = season
    if bookmaker:
        params["bookmaker"] = bookmaker
    if market:
        params["bet"] = market
    if not params:
        raise ValueError("Au moins un filtre odds est requis: --date, --fixture-id, --league-id/--season, --bookmaker ou --market.")
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{base_url}/odds?{query}", headers={"x-apisports-key": key})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8")
            payload = json.loads(text) if text else {}
            payload["_http_status"] = response.status
            return payload
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return {"response": [], "errors": {"http": body or str(exc)}, "_http_status": exc.code}
    except Exception as exc:
        return {"response": [], "errors": {"exception": str(exc)}, "_http_status": None}


def fetch_api_football(league: str, date: str, config: Dict[str, Any]) -> Dict[str, Any]:
    return fetch_api_football_odds(config, date=date, league_id=league)


def write_rows(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    return write_normalized_csv(rows, output)


def write_raw(payload: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _filter_rows(rows: List[Dict[str, Any]], market: str = "", bookmaker: str = "", valid_only: bool = False) -> List[Dict[str, Any]]:
    out = []
    for row in rows:
        if market and row.get("market_type") != market:
            continue
        if bookmaker and str(row.get("bookmaker") or "").lower() != bookmaker.lower():
            continue
        if valid_only and row.get("validation_status") != "valid":
            continue
        out.append(row)
    return out


def _limit_one_side_per_event(rows: List[Dict[str, Any]], max_events: int = 0, prefer_side: str = "") -> List[Dict[str, Any]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("source_event_id") or row.get("snapshot_id") or ""), []).append(row)
    out: List[Dict[str, Any]] = []
    side_order = [prefer_side] if prefer_side else []
    side_order.extend(["home", "away", "draw"])
    for _, event_rows in sorted(grouped.items(), key=lambda item: (item[1][0].get("match_date") or "", item[0])):
        chosen = None
        for side in side_order:
            if not side:
                continue
            chosen = next((row for row in event_rows if row.get("side") == side), None)
            if chosen:
                break
        chosen = chosen or event_rows[0]
        out.append(chosen)
        if max_events and len(out) >= max_events:
            break
    return out


def summarize_rows(rows: List[Dict[str, Any]], raw_count: int = 0, fixtures_loaded: int = 0, enriched_count: int = 0) -> Dict[str, Any]:
    valid = [row for row in rows if row.get("validation_status") == "valid"]
    invalid = [row for row in rows if row.get("validation_status") != "valid"]
    def counts(key: str) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for row in rows:
            value = row.get(key) or "unknown"
            out[value] = out.get(value, 0) + 1
        return dict(sorted(out.items(), key=lambda item: item[1], reverse=True)[:20])
    return {
        "raw_odds_lines": raw_count,
        "fixtures_loaded": fixtures_loaded,
        "rows_enriched_with_teams": enriched_count,
        "rows_total": len(rows),
        "valid_rows": len(valid),
        "invalid_rows": len(invalid),
        "events_total": len({row.get("source_event_id") for row in rows if row.get("source_event_id")}),
        "events_valid": len({row.get("source_event_id") for row in valid if row.get("source_event_id")}),
        "top_leagues": counts("league"),
        "top_bookmakers": counts("bookmaker"),
        "top_markets": counts("market_type"),
        "invalid_reasons": counts("validation_reason"),
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_summary_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_summary_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    blocks = "".join(
        f"<section><h2>{html.escape(str(key))}</h2><pre>{html.escape(json.dumps(value, ensure_ascii=False, indent=2))}</pre></section>"
        for key, value in report.items()
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>API-Football Odds Summary</h1>"
        + blocks
        + "<p>Laboratoire local, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def process_payload(
    payload: Dict[str, Any],
    fixtures_index: Dict[str, Dict[str, Any]] | None = None,
    market: str = "",
    bookmaker: str = "",
    valid_only: bool = False,
    one_side_per_event: bool = False,
    prefer_side: str = "",
    max_events: int = 0,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    raw_rows = _fixture_rows(payload)
    fixtures_index = fixtures_index or {}
    enriched_raw, enriched_count = enrich_raw_rows_with_fixtures(raw_rows, fixtures_index)
    normalized = normalize_odds_rows(enriched_raw, source="api_football")
    filtered = _filter_rows(normalized, market=market, bookmaker=bookmaker, valid_only=valid_only)
    if one_side_per_event:
        filtered = _limit_one_side_per_event(filtered, max_events=max_events, prefer_side=prefer_side)
    elif max_events:
        allowed_events = []
        for row in filtered:
            event_id = row.get("source_event_id")
            if event_id not in allowed_events:
                allowed_events.append(event_id)
            if len(allowed_events) >= max_events:
                break
        filtered = [row for row in filtered if row.get("source_event_id") in set(allowed_events)]
    invalid = [row for row in normalized if row.get("validation_status") != "valid"]
    summary = summarize_rows(filtered, raw_count=len(raw_rows), fixtures_loaded=len(fixtures_index), enriched_count=enriched_count)
    summary["pre_filter_rows_total"] = len(normalized)
    summary["pre_filter_valid_rows"] = sum(1 for row in normalized if row.get("validation_status") == "valid")
    summary["pre_filter_invalid_rows"] = len(invalid)
    summary["filters"] = {"market": market, "bookmaker": bookmaker, "valid_only": valid_only, "one_side_per_event": one_side_per_event, "prefer_side": prefer_side, "max_events": max_events}
    return filtered, invalid, summary


def response_warnings(payload: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    if payload.get("_http_status") not in (None, 200):
        warnings.append(f"HTTP status {payload.get('_http_status')}")
    errors = payload.get("errors")
    if errors:
        warnings.append("erreurs API-Football: " + json.dumps(errors, ensure_ascii=False))
    if not payload.get("response"):
        warnings.append("aucune cote retournee; endpoint odds peut exiger fixture/league/season/bookmaker selon le plan")
    return warnings


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Adaptateur API-Football odds, reseau desactive par defaut.")
    parser.add_argument("--check-config", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--league", default="")
    parser.add_argument("--league-id", default="")
    parser.add_argument("--fixture-id", default="")
    parser.add_argument("--season", default="")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--market", default="")
    parser.add_argument("--date", default="")
    parser.add_argument("--from-fixture", default="")
    parser.add_argument("--fixtures-csv", default="")
    parser.add_argument("--fixtures-json", default="")
    parser.add_argument("--auto-fixtures", action="store_true")
    parser.add_argument("--require-teams", default="true")
    parser.add_argument("--valid-only", action="store_true")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--one-side-per-event", action="store_true")
    parser.add_argument("--prefer-side", default="")
    parser.add_argument("--output-invalid", default="")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--raw-output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_odds_source_config()
        if args.check_config:
            report = validate_config(config)
            print("API-Football odds adapter")
            print(f"- Configuration: {'OK' if report['ok'] else 'bloquante'}")
            print(f"- Cle API: {'presente' if get_api_key_from_env('api_football', config) else 'absente'}")
            print("- Aucun reseau lance par --check-config.")
            return 0 if report["ok"] else 1
        if args.dry_run:
            print("API-Football dry-run")
            print(f"- Ligue: {args.league_id or args.league or 'n/a'}")
            print(f"- Fixture: {args.fixture_id or 'n/a'}")
            print(f"- Date: {args.date or 'n/a'}")
            print("- Aucun reseau lance. Ajouter --allow-network explicitement pour une vraie requete.")
            return 0
        if args.from_fixture:
            payload = read_fixture(args.from_fixture)
            fixtures_index = load_fixture_index(args.fixtures_csv, args.fixtures_json)
            rows, invalid_rows, summary = process_payload(
                payload,
                fixtures_index=fixtures_index,
                market=args.market,
                bookmaker=args.bookmaker,
                valid_only=args.valid_only,
                one_side_per_event=args.one_side_per_event,
                prefer_side=args.prefer_side,
                max_events=args.max_events,
            )
            print(f"- Fixture lue: {args.from_fixture}")
            print(f"- Fixtures chargees: {len(fixtures_index)}")
            print(f"- Lignes normalisees: {summary.get('pre_filter_rows_total')}")
            print(f"- Lignes enrichies avec equipes: {summary.get('rows_enriched_with_teams')}")
            print(f"- Lignes validees: {summary.get('valid_rows')}")
            print(f"- Lignes invalides: {summary.get('pre_filter_invalid_rows')}")
            if args.output:
                print(f"- Sortie ecrite: {write_rows(rows, args.output)}")
            if args.output_invalid:
                print(f"- Invalides ecrites: {write_rows(invalid_rows, args.output_invalid)}")
            if args.summary_json:
                print(f"- Summary JSON ecrit: {write_summary_json(summary, args.summary_json)}")
            if args.html:
                print(f"- Summary HTML ecrit: {write_summary_html(summary, args.html)}")
            return 0
        if not args.allow_network:
            raise ValueError("Reseau refuse par defaut. Utiliser --dry-run ou --allow-network.")
        fixtures_index = load_fixture_index(args.fixtures_csv, args.fixtures_json)
        if args.auto_fixtures:
            if not args.date:
                raise ValueError("--date requis avec --auto-fixtures")
            fixtures_payload = fetch_fixtures(args.date, config)
            fixtures_index.update(_fixture_index(normalize_fixtures_payload(fixtures_payload)))
        elif not fixtures_index:
            print("- Warning: fixtures absentes: odds non enrichies.")
        payload = fetch_api_football_odds(
            config,
            date=args.date,
            fixture_id=args.fixture_id,
            league_id=args.league_id or args.league,
            season=args.season,
            bookmaker=args.bookmaker,
            market=args.market,
        )
        if args.raw_output:
            print(f"- Raw output ecrit: {write_raw(payload, args.raw_output)}")
        rows, invalid_rows, summary = process_payload(
            payload,
            fixtures_index=fixtures_index,
            market=args.market,
            bookmaker=args.bookmaker,
            valid_only=args.valid_only,
            one_side_per_event=args.one_side_per_event,
            prefer_side=args.prefer_side,
            max_events=args.max_events,
        )
        print(f"- Lignes odds brutes: {summary.get('raw_odds_lines')}")
        print(f"- Fixtures chargees: {summary.get('fixtures_loaded')}")
        print(f"- Lignes enrichies avec equipes: {summary.get('rows_enriched_with_teams')}")
        print(f"- Lignes validees: {summary.get('valid_rows')}")
        print(f"- Lignes invalides: {summary.get('pre_filter_invalid_rows')}")
        print(f"- Top ligues: {summary.get('top_leagues')}")
        print(f"- Top bookmakers: {summary.get('top_bookmakers')}")
        print(f"- Top markets: {summary.get('top_markets')}")
        for warning in response_warnings(payload):
            print(f"- Warning: {warning}")
        if args.output:
            print(f"- Sortie ecrite: {write_rows(rows, args.output)}")
        if args.output_invalid:
            print(f"- Invalides ecrites: {write_rows(invalid_rows, args.output_invalid)}")
        if args.summary_json:
            print(f"- Summary JSON ecrit: {write_summary_json(summary, args.summary_json)}")
        if args.html:
            print(f"- Summary HTML ecrit: {write_summary_html(summary, args.html)}")
        print("- API-Football peut etre utile au laboratoire, mais ne prouve pas une closing historique parfaite.")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
