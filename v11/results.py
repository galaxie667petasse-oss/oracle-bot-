"""Apply postmatch provider observations through explicit fixture mappings."""
from datetime import datetime

from api_football_results_adapter import normalize_results_payload
from v10.time import parse_utc
from v11.ledger import Ledger
from v11.markets import settle


def apply_results(ledger: Ledger, envelope: dict, fixture_map: dict[str, str], now: datetime,
                  team_map: dict[str, str] | None = None) -> dict:
    if envelope.get("provider") != "api_football" or envelope["payload"].get("errors"):
        raise ValueError("valid API-Football result envelope required")
    observed = parse_utc(envelope["fetched_at"])
    if observed > now:
        raise ValueError("future result observation")
    rows = normalize_results_payload(envelope["payload"])
    result_rows = {}
    for row in rows:
        key = "api_football:" + row["fixture_id"]
        if key in result_rows:
            raise ValueError("duplicate result identity")
        result_rows[key] = row
    team_map = team_map or {}
    planned, pending = [], []
    for fixture_id, external_id in fixture_map.items():
        row = result_rows.get(external_id)
        if row is None or row["status"] != "FT":
            pending.append({"fixture_id": fixture_id, "reason": "regulation_result_not_available"})
            continue
        if row["validation_status"] != "valid":
            raise ValueError("invalid result observation")
        home, away = int(row["home_goals"]), int(row["away_goals"])
        settle("match_winner", "home", 2, home, away)
        predictions = ledger.predictions_for_fixture(fixture_id)
        if not predictions:
            pending.append({"fixture_id": fixture_id, "reason": "no_sealed_prediction"})
        for pred in predictions:
            if (pred["home"], pred["away"], parse_utc(pred["kickoff"])) != (
                    team_map.get(row["home_team"], row["home_team"]),
                    team_map.get(row["away_team"], row["away_team"]), parse_utc(row["kickoff_time"])):
                raise ValueError("mapped result conflicts with sealed fixture identity")
            if observed <= parse_utc(pred["kickoff"]):
                raise ValueError("result observation must follow kickoff")
            planned.append((pred["id"], home, away, external_id))
    # Validate the entire batch before the first write. Replaying a batch is idempotent.
    ids = [ledger.add_outcome(key, h, a, observed, source) for key, h, a, source in planned]
    return {"status": "PASS" if not pending else "PARTIAL", "outcome_ids": ids, "pending": pending,
            "observed_at": observed.isoformat(), "can_influence_picks": False}
