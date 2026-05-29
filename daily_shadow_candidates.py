import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from shadow_ledger import add_shadow_entry, read_ledger


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
    "no_vig_probability",
    "edge",
    "edge_probability",
    "strategy_name",
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


def _status(edge: Optional[float], odds: Optional[float], has_core_data: bool = True) -> str:
    if odds is None or odds <= 1.01:
        return "no_odds"
    if not has_core_data:
        return "insufficient_data"
    if edge is None:
        return "insufficient_data"
    if edge > 0.03:
        return "watchlist"
    if edge > 0:
        return "observation"
    return "rejected"


def _dedupe_key(row: Dict[str, Any]) -> tuple:
    return (
        str(row.get("match_date") or "").lower(),
        str(row.get("league") or "").lower(),
        str(row.get("home_team") or "").lower(),
        str(row.get("away_team") or "").lower(),
        str(row.get("market_type") or "").lower(),
        str(row.get("side") or "").lower(),
        str(row.get("odds") or "").replace(",", "."),
    )


def build_daily_candidates(features_path: str, date: str = "", output: str = "reports/daily_shadow_candidates.csv", to_ledger: str = "") -> Dict[str, Any]:
    source = Path(features_path)
    if not source.exists():
        raise FileNotFoundError(f"CSV features/matchs introuvable: {features_path}")
    target = ensure_reports_path(output)
    candidates: List[Dict[str, Any]] = []
    rows_seen = 0
    with source.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            row_date = _date(row)
            if date and row_date != date:
                continue
            rows_seen += 1
            odds = _float(_first(row, "odds", "taken_odds", "OddHome"))
            model_probability = _float(_first(row, "model_probability", "signal_probability", "predicted_probability"))
            market_probability = _float(_first(row, "market_probability", "no_vig_probability", "implied_probability"))
            no_vig_probability = _float(_first(row, "no_vig_probability"))
            edge_probability = _float(_first(row, "edge_probability", "edge"))
            edge = edge_probability
            if edge is None and model_probability is not None and market_probability is not None:
                edge = model_probability - market_probability
            has_core = bool(_first(row, "home_team", "home", "HomeTeam") and _first(row, "away_team", "away", "AwayTeam") and _first(row, "market_type", "market"))
            status = _status(edge, odds, has_core_data=has_core)
            reason = "observation shadow sans recommandation de mise"
            if status == "rejected":
                reason = "rejete pour shadow: edge absent/faible ou cote invalide"
            elif status == "no_odds":
                reason = "cote absente: observation non exploitable"
            elif status == "insufficient_data":
                reason = "donnees insuffisantes pour observation shadow"
            candidates.append({
                "match_date": row_date,
                "league": _first(row, "league", "competition", "Div"),
                "home_team": _first(row, "home_team", "home", "HomeTeam"),
                "away_team": _first(row, "away_team", "away", "AwayTeam"),
                "market_type": _first(row, "market_type", "market"),
                "side": _side(row),
                "odds": "" if odds is None else odds,
                "model_probability": "" if model_probability is None else model_probability,
                "market_probability": "" if market_probability is None else market_probability,
                "no_vig_probability": "" if no_vig_probability is None else no_vig_probability,
                "edge": "" if edge is None else round(edge, 8),
                "edge_probability": "" if edge_probability is None else edge_probability,
                "strategy_name": _first(row, "strategy_name", "strategy"),
                "reason": reason,
                "status": status,
            })
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CANDIDATE_COLUMNS)
        writer.writeheader()
        for row in candidates:
            writer.writerow(row)
    ledger_added = 0
    ledger_duplicates = 0
    ledger_errors: List[str] = []
    if to_ledger:
        existing_keys = {
            (
                row.get("match_date", "").lower(),
                row.get("league", "").lower(),
                row.get("home_team", "").lower(),
                row.get("away_team", "").lower(),
                row.get("market_type", "").lower(),
                row.get("side", "").lower(),
                str(row.get("taken_odds") or "").replace(",", "."),
            )
            for row in read_ledger(to_ledger)
        }
        for row in candidates:
            key = (
                str(row.get("match_date") or "").lower(),
                str(row.get("league") or "").lower(),
                str(row.get("home_team") or "").lower(),
                str(row.get("away_team") or "").lower(),
                str(row.get("market_type") or "").lower(),
                str(row.get("side") or "").lower(),
                str(row.get("odds") or "").replace(",", "."),
            )
            if key in existing_keys:
                ledger_duplicates += 1
                continue
            if row["status"] == "no_odds":
                ledger_errors.append(f"{row.get('match_date')} {row.get('home_team')}-{row.get('away_team')}: cote absente")
                continue
            try:
                add_shadow_entry(
                    to_ledger,
                    match_date=row.get("match_date"),
                    league=row.get("league"),
                    home_team=row.get("home_team"),
                    away_team=row.get("away_team"),
                    market_type=row.get("market_type"),
                    side=row.get("side"),
                    taken_odds=row.get("odds"),
                    strategy_name=row.get("strategy_name"),
                    reason=row.get("reason"),
                    signal_probability=row.get("model_probability"),
                    market_probability=row.get("market_probability"),
                    no_vig_probability=row.get("no_vig_probability"),
                    edge_probability=row.get("edge") or row.get("edge_probability"),
                    status=row.get("status") if row.get("status") in {"observation", "watchlist", "rejected"} else "observation",
                )
                existing_keys.add(key)
                ledger_added += 1
            except Exception as exc:
                ledger_errors.append(str(exc))
    return {
        "features_path": features_path,
        "date": date,
        "output": str(target),
        "rows_for_date": rows_seen,
        "candidates_written": len(candidates),
        "watchlist": sum(1 for row in candidates if row["status"] == "watchlist"),
        "observation": sum(1 for row in candidates if row["status"] == "observation"),
        "rejected": sum(1 for row in candidates if row["status"] == "rejected"),
        "no_odds": sum(1 for row in candidates if row["status"] == "no_odds"),
        "insufficient_data": sum(1 for row in candidates if row["status"] == "insufficient_data"),
        "ledger_path": to_ledger,
        "ledger_added": ledger_added,
        "ledger_duplicates": ledger_duplicates,
        "ledger_errors": ledger_errors,
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
    print(f"- Watchlist/observation/rejected/no_odds/insufficient_data: {summary.get('watchlist')} / {summary.get('observation')} / {summary.get('rejected')} / {summary.get('no_odds')} / {summary.get('insufficient_data')}")
    if summary.get("ledger_path"):
        print(f"- Ajouts ledger: {summary.get('ledger_added')}")
        print(f"- Doublons ledger: {summary.get('ledger_duplicates')}")
        for error in summary.get("ledger_errors") or []:
            print(f"  - Erreur ledger: {error}")
    if summary.get("candidates_written") == 0:
        print("- Aucun match trouve a cette date.")
    print("- Aucune recommandation de mise, aucune mise, aucun Telegram.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare des candidats shadow depuis un CSV, sans conseiller de mise.")
    parser.add_argument("--features", default="", help="CSV historique")
    parser.add_argument("--input", default="", help="CSV de candidats live ou manuel")
    parser.add_argument("--date", default="", help="Date YYYY-MM-DD")
    parser.add_argument("--output", default="reports/daily_shadow_candidates.csv")
    parser.add_argument("--to-ledger", default="", help="Ajoute les observations au shadow ledger")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        source = args.input or args.features
        if not source:
            raise ValueError("--input ou --features est requis")
        summary = build_daily_candidates(source, args.date, args.output, to_ledger=args.to_ledger)
        print_summary(summary)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
