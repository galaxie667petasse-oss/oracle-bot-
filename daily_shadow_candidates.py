import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional


CANDIDATE_COLUMNS = [
    "match_date",
    "league",
    "home_team",
    "away_team",
    "market_type",
    "side",
    "odds",
    "model_probability",
    "market_probability",
    "edge",
    "reason",
    "status",
]


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les candidats shadow ne doivent pas etre ecrits dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _first(row: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip().replace(",", "."))
    except Exception:
        return None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "oui", "y"}


def _side(row: Dict[str, Any]) -> str:
    market = _first(row, "market_type", "market").lower()
    pari = _first(row, "pari", "selection", "side").lower()
    if _truthy(row.get("is_home_pick")) or pari in {"home", "domicile"}:
        return "home"
    if _truthy(row.get("is_away_pick")) or pari in {"away", "exterieur"}:
        return "away"
    if _truthy(row.get("is_draw")) or market == "draw" or "draw" in pari or "nul" in pari:
        return "draw"
    if _truthy(row.get("is_over")) or "over" in pari or "plus" in pari:
        return "over"
    if _truthy(row.get("is_under")) or "under" in pari or "moins" in pari:
        return "under"
    return _first(row, "side") or "unknown"


def _date(row: Dict[str, Any]) -> str:
    return _first(row, "match_date", "date", "date_key", "Date")[:10]


def _status(edge: Optional[float], odds: Optional[float]) -> str:
    if edge is None or odds is None or odds <= 1.01:
        return "rejected"
    if edge > 0.03:
        return "watchlist"
    if edge > 0:
        return "observation"
    return "rejected"


def build_daily_candidates(features_path: str, date: str, output: str) -> Dict[str, Any]:
    source = Path(features_path)
    if not source.exists():
        raise FileNotFoundError(f"CSV features/matchs introuvable: {features_path}")
    target = ensure_reports_path(output)
    candidates: List[Dict[str, Any]] = []
    rows_seen = 0
    with source.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if _date(row) != date:
                continue
            rows_seen += 1
            odds = _float(_first(row, "odds", "taken_odds", "OddHome"))
            model_probability = _float(_first(row, "model_probability", "signal_probability", "predicted_probability"))
            market_probability = _float(_first(row, "market_probability", "no_vig_probability", "implied_probability"))
            edge = _float(_first(row, "edge", "edge_probability"))
            if edge is None and model_probability is not None and market_probability is not None:
                edge = model_probability - market_probability
            status = _status(edge, odds)
            reason = "observation shadow sans conseil de mise"
            if status == "rejected":
                reason = "rejete pour shadow: edge absent/faible ou cote invalide"
            candidates.append({
                "match_date": date,
                "league": _first(row, "league", "competition", "Div"),
                "home_team": _first(row, "home_team", "home", "HomeTeam"),
                "away_team": _first(row, "away_team", "away", "AwayTeam"),
                "market_type": _first(row, "market_type", "market"),
                "side": _side(row),
                "odds": "" if odds is None else odds,
                "model_probability": "" if model_probability is None else model_probability,
                "market_probability": "" if market_probability is None else market_probability,
                "edge": "" if edge is None else round(edge, 8),
                "reason": reason,
                "status": status,
            })
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDIDATE_COLUMNS)
        writer.writeheader()
        for row in candidates:
            writer.writerow(row)
    return {
        "features_path": features_path,
        "date": date,
        "output": str(target),
        "rows_for_date": rows_seen,
        "candidates_written": len(candidates),
        "watchlist": sum(1 for row in candidates if row["status"] == "watchlist"),
        "observation": sum(1 for row in candidates if row["status"] == "observation"),
        "rejected": sum(1 for row in candidates if row["status"] == "rejected"),
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_summary(summary: Dict[str, Any]) -> None:
    print("Daily Shadow Candidates Oracle Bot")
    print(f"- CSV source: {summary.get('features_path')}")
    print(f"- Date: {summary.get('date')}")
    print(f"- Sortie: {summary.get('output')}")
    print(f"- Lignes a la date: {summary.get('rows_for_date')}")
    print(f"- Candidats shadow ecrits: {summary.get('candidates_written')}")
    print(f"- Watchlist/observation/rejected: {summary.get('watchlist')} / {summary.get('observation')} / {summary.get('rejected')}")
    if summary.get("candidates_written") == 0:
        print("- Aucun match trouve a cette date.")
    print("- Aucun conseil de pari, aucune mise, aucun Telegram.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare des candidats shadow depuis un CSV, sans conseiller de pari.")
    parser.add_argument("--features", required=True, help="CSV historique ou futur CSV live")
    parser.add_argument("--date", required=True, help="Date YYYY-MM-DD")
    parser.add_argument("--output", default="reports/daily_shadow_candidates.csv")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        summary = build_daily_candidates(args.features, args.date, args.output)
        print_summary(summary)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
