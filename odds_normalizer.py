import csv
import hashlib
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from team_name_normalizer import normalize_team_name


ODDS_COLUMNS = [
    "snapshot_id",
    "captured_at",
    "source",
    "source_event_id",
    "league",
    "match_date",
    "kickoff_time",
    "home_team",
    "away_team",
    "bookmaker",
    "market_type",
    "side",
    "odds",
    "odds_format",
    "is_live",
    "is_near_close",
    "raw_market",
    "raw_side",
    "raw_payload_ref",
    "normalized_home",
    "normalized_away",
    "validation_status",
    "validation_reason",
]

VALID_MARKETS = {"h2h", "draw", "total", "btts", "handicap", "unknown"}
VALID_SIDES = {"home", "away", "draw", "over", "under", "yes", "no", "unknown"}


def normalize_decimal_odds(value: Any) -> float:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        raise ValueError("cote absente")
    try:
        number = float(text)
    except Exception:
        raise ValueError("cote non numerique")
    if not math.isfinite(number):
        raise ValueError("cote non finie")
    if number <= 1.01:
        raise ValueError("cote <= 1.01 ou valeur de probabilite probable")
    if number >= 100:
        raise ValueError("cote trop grande pour le laboratoire")
    return round(number, 6)


def normalize_bool(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "oui", "vrai"}:
        return "True"
    return "False"


def normalize_market_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace("/", "_").replace(" ", "_")
    if text in {"h2h", "1x2", "match_winner", "winner", "full_time_result", "home_draw_away"}:
        return "h2h"
    if text in {"draw"}:
        return "draw"
    if text in {"total", "totals", "over_under", "goals_over_under", "ou", "o_u"}:
        return "total"
    if text in {"btts", "both_teams_to_score", "both_teams_score"}:
        return "btts"
    if "handicap" in text or "spread" in text:
        return "handicap"
    return "unknown"


def normalize_side(value: Any, market_type: str = "unknown", home_team: str = "", away_team: str = "") -> str:
    text = str(value or "").strip().lower().replace("-", " ").replace("_", " ")
    home_norm = normalize_team_name(home_team).lower() if home_team else ""
    away_norm = normalize_team_name(away_team).lower() if away_team else ""
    compact = " ".join(text.split())
    if compact in {"home", "h", "1", "domicile", "equipe 1"} or (home_norm and normalize_team_name(text).lower() == home_norm):
        return "home"
    if compact in {"away", "a", "2", "exterieur", "equipe 2"} or (away_norm and normalize_team_name(text).lower() == away_norm):
        return "away"
    if compact in {"draw", "d", "x", "nul"}:
        return "draw"
    if compact.startswith("over") or compact.startswith("plus") or compact in {"o", "over"}:
        return "over"
    if compact.startswith("under") or compact.startswith("moins") or compact in {"u", "under"}:
        return "under"
    if compact in {"yes", "oui", "y"}:
        return "yes"
    if compact in {"no", "non", "n"}:
        return "no"
    return "unknown"


def build_snapshot_id(row: Dict[str, Any]) -> str:
    key_parts = [
        str(row.get("captured_at") or ""),
        str(row.get("source") or ""),
        str(row.get("source_event_id") or ""),
        str(row.get("league") or ""),
        str(row.get("match_date") or ""),
        str(row.get("home_team") or row.get("normalized_home") or ""),
        str(row.get("away_team") or row.get("normalized_away") or ""),
        str(row.get("bookmaker") or ""),
        str(row.get("market_type") or ""),
        str(row.get("side") or ""),
        str(row.get("odds") or ""),
    ]
    digest = hashlib.sha1("|".join(key_parts).lower().encode("utf-8")).hexdigest()[:16]
    return f"odds_{digest}"


def validate_odds_row(row: Dict[str, Any]) -> Dict[str, Any]:
    normalized = {column: str(row.get(column, "") or "").strip() for column in ODDS_COLUMNS}
    normalized["captured_at"] = normalized["captured_at"] or datetime.now().isoformat(timespec="seconds")
    normalized["source"] = normalized["source"] or str(row.get("source") or "manual_csv")
    normalized["league"] = normalized["league"] or str(row.get("competition") or "").strip()
    normalized["home_team"] = normalized["home_team"] or str(row.get("home") or "").strip()
    normalized["away_team"] = normalized["away_team"] or str(row.get("away") or "").strip()
    normalized["market_type"] = normalize_market_type(normalized["market_type"] or row.get("market") or row.get("raw_market"))
    normalized["side"] = normalize_side(normalized["side"] or row.get("raw_side"), normalized["market_type"], normalized["home_team"], normalized["away_team"])
    normalized["odds_format"] = "decimal"
    normalized["is_live"] = normalize_bool(normalized["is_live"])
    normalized["is_near_close"] = normalize_bool(normalized["is_near_close"])
    normalized["normalized_home"] = normalize_team_name(normalized["home_team"], league=normalized["league"]) if normalized["home_team"] else ""
    normalized["normalized_away"] = normalize_team_name(normalized["away_team"], league=normalized["league"]) if normalized["away_team"] else ""
    errors = []
    try:
        normalized["odds"] = str(normalize_decimal_odds(normalized["odds"] or row.get("price")))
    except Exception as exc:
        errors.append(str(exc))
    if normalized["market_type"] not in VALID_MARKETS:
        errors.append("marche inconnu")
    if normalized["side"] not in VALID_SIDES or normalized["side"] == "unknown":
        errors.append("side inconnu")
    if not normalized["match_date"]:
        errors.append("date match absente")
    if not normalized["home_team"] or not normalized["away_team"]:
        errors.append("equipes absentes")
    normalized["validation_status"] = "invalid" if errors else "valid"
    normalized["validation_reason"] = "; ".join(errors) if errors else "ok"
    normalized["snapshot_id"] = normalized["snapshot_id"] or build_snapshot_id(normalized)
    return {column: normalized.get(column, "") for column in ODDS_COLUMNS}


def normalize_odds_rows(rows: Iterable[Dict[str, Any]], source: str = "manual_csv") -> List[Dict[str, Any]]:
    normalized_rows = []
    for row in rows:
        payload = dict(row)
        payload["source"] = payload.get("source") or source
        normalized_rows.append(validate_odds_row(payload))
    return normalized_rows


def write_normalized_csv(rows: Iterable[Dict[str, Any]], output: str) -> Path:
    target = Path(output)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les snapshots de cotes ne doivent pas etre ecrits dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ODDS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in ODDS_COLUMNS})
    return target
