import argparse
import csv
import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


DEFAULT_LEDGER = "reports/shadow_ledger.csv"
LEDGER_COLUMNS = [
    "shadow_id",
    "created_at",
    "match_date",
    "league",
    "home_team",
    "away_team",
    "market_type",
    "side",
    "taken_odds",
    "bookmaker",
    "signal_probability",
    "market_probability",
    "no_vig_probability",
    "edge_probability",
    "model_name",
    "strategy_name",
    "confidence_label",
    "reason",
    "status",
    "result",
    "closing_odds",
    "closing_source",
    "clv_percent",
    "clv_available",
    "notes",
]
VALID_STATUS = {"observation", "watchlist", "rejected", "pending_result", "settled"}
VALID_RESULT = {"win", "loss", "push", "unknown"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ensure_writable_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le shadow ledger ne doit jamais etre ecrit dans data/. Utiliser reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def parse_decimal_odds(value: Any, field_name: str) -> float:
    try:
        number = float(str(value).strip().replace(",", "."))
    except Exception:
        raise ValueError(f"{field_name} doit etre numerique.")
    if not math.isfinite(number) or number <= 1.01:
        raise ValueError(f"{field_name} doit etre une cote decimale > 1.01.")
    return number


def optional_float(value: Any) -> str:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return ""
    try:
        number = float(text)
    except Exception:
        raise ValueError("Une probabilite optionnelle doit etre numerique.")
    if not math.isfinite(number):
        raise ValueError("Une probabilite optionnelle doit etre finie.")
    return str(number)


def init_ledger(path: str = DEFAULT_LEDGER) -> Path:
    target = ensure_writable_path(path)
    if not target.exists():
        with target.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS)
            writer.writeheader()
    return target


def read_ledger(path: str = DEFAULT_LEDGER) -> List[Dict[str, str]]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        return [dict(row) for row in reader]


def write_ledger(rows: Iterable[Dict[str, Any]], path: str = DEFAULT_LEDGER) -> Path:
    target = ensure_writable_path(path)
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=LEDGER_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in LEDGER_COLUMNS})
    return target


def compute_clv(taken_odds: float, closing_odds: Optional[float]) -> Dict[str, Any]:
    if closing_odds is None:
        return {"clv_percent": "", "clv_available": "False"}
    return {
        "clv_percent": round(taken_odds / closing_odds - 1.0, 8),
        "clv_available": "True",
    }


def add_shadow_entry(path: str = DEFAULT_LEDGER, **kwargs: Any) -> Dict[str, Any]:
    init_ledger(path)
    taken_odds = parse_decimal_odds(kwargs.get("taken_odds"), "taken_odds")
    closing_raw = kwargs.get("closing_odds")
    closing_odds = parse_decimal_odds(closing_raw, "closing_odds") if str(closing_raw or "").strip() else None
    status = str(kwargs.get("status") or "observation").strip()
    result = str(kwargs.get("result") or "unknown").strip()
    if status not in VALID_STATUS:
        raise ValueError(f"status invalide: {status}")
    if result not in VALID_RESULT:
        raise ValueError(f"result invalide: {result}")
    entry: Dict[str, Any] = {
        "shadow_id": str(kwargs.get("shadow_id") or f"sh_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"),
        "created_at": now_iso(),
        "match_date": str(kwargs.get("match_date") or "").strip(),
        "league": str(kwargs.get("league") or "").strip(),
        "home_team": str(kwargs.get("home_team") or kwargs.get("home") or "").strip(),
        "away_team": str(kwargs.get("away_team") or kwargs.get("away") or "").strip(),
        "market_type": str(kwargs.get("market_type") or kwargs.get("market") or "").strip().lower(),
        "side": str(kwargs.get("side") or "").strip().lower(),
        "taken_odds": taken_odds,
        "bookmaker": str(kwargs.get("bookmaker") or "").strip(),
        "signal_probability": optional_float(kwargs.get("signal_probability")),
        "market_probability": optional_float(kwargs.get("market_probability")),
        "no_vig_probability": optional_float(kwargs.get("no_vig_probability")),
        "edge_probability": optional_float(kwargs.get("edge_probability")),
        "model_name": str(kwargs.get("model_name") or "").strip(),
        "strategy_name": str(kwargs.get("strategy_name") or "").strip(),
        "confidence_label": str(kwargs.get("confidence_label") or "").strip(),
        "reason": str(kwargs.get("reason") or "").strip(),
        "status": status,
        "result": result,
        "closing_odds": "" if closing_odds is None else closing_odds,
        "closing_source": str(kwargs.get("closing_source") or "").strip(),
        "notes": str(kwargs.get("notes") or "").strip(),
    }
    entry.update(compute_clv(taken_odds, closing_odds))
    rows = read_ledger(path)
    rows.append(entry)
    write_ledger(rows, path)
    return entry


def summarize_ledger(path: str = DEFAULT_LEDGER) -> Dict[str, Any]:
    rows = read_ledger(path)
    clvs = []
    status_counts: Dict[str, int] = {}
    result_counts: Dict[str, int] = {}
    for row in rows:
        status_counts[row.get("status", "")] = status_counts.get(row.get("status", ""), 0) + 1
        result_counts[row.get("result", "")] = result_counts.get(row.get("result", ""), 0) + 1
        if str(row.get("clv_available") or "").lower() == "true":
            try:
                clvs.append(float(row.get("clv_percent") or 0))
            except Exception:
                pass
    return {
        "ledger": path,
        "signals_total": len(rows),
        "signals_with_clv": len(clvs),
        "clv_coverage": round(len(clvs) / len(rows) * 100.0, 2) if rows else 0.0,
        "clv_mean": round(sum(clvs) / len(clvs), 6) if clvs else None,
        "clv_positive_rate": round(sum(1 for value in clvs if value > 0) / len(clvs) * 100.0, 2) if clvs else None,
        "status_counts": status_counts,
        "result_counts": result_counts,
        "lab_only": True,
        "can_influence_picks": False,
    }


def export_ledger(path: str, output: str) -> Path:
    rows = read_ledger(path)
    target = ensure_writable_path(output)
    write_ledger(rows, str(target))
    return target


def print_rows(rows: List[Dict[str, str]]) -> None:
    print("Shadow ledger Oracle Bot")
    if not rows:
        print("- Aucun signal shadow enregistre.")
        return
    for row in rows:
        print(
            f"- {row.get('shadow_id')} | {row.get('match_date')} | {row.get('league')} | "
            f"{row.get('home_team')} - {row.get('away_team')} | {row.get('market_type')} {row.get('side')} | "
            f"cote={row.get('taken_odds')} | statut={row.get('status')} | CLV={row.get('clv_percent') or 'n/a'}"
        )


def print_summary(summary: Dict[str, Any]) -> None:
    print("Resume shadow ledger Oracle Bot")
    print(f"- Ledger: {summary.get('ledger')}")
    print(f"- Signaux shadow: {summary.get('signals_total')}")
    print(f"- Signaux avec CLV: {summary.get('signals_with_clv')}")
    print(f"- Coverage CLV: {summary.get('clv_coverage')}%")
    print(f"- CLV moyenne: {summary.get('clv_mean')}")
    print(f"- CLV positive: {summary.get('clv_positive_rate')}%")
    print(f"- Statuts: {json.dumps(summary.get('status_counts'), ensure_ascii=False)}")
    print("- Observation seulement: aucune mise, aucun pick automatique.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Journal local des signaux shadow Oracle Bot, sans conseil de pari.")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help="Chemin du ledger CSV, par defaut reports/shadow_ledger.csv")
    parser.add_argument("--init", action="store_true", help="Initialise le ledger")
    parser.add_argument("--add", action="store_true", help="Ajoute un signal shadow")
    parser.add_argument("--list", action="store_true", help="Liste les signaux shadow")
    parser.add_argument("--summary", action="store_true", help="Resume le ledger")
    parser.add_argument("--export", default="", help="Exporte le ledger vers un CSV dans reports/")
    parser.add_argument("--match-date", default="")
    parser.add_argument("--league", default="")
    parser.add_argument("--home", default="")
    parser.add_argument("--away", default="")
    parser.add_argument("--market", default="", dest="market_type")
    parser.add_argument("--side", default="")
    parser.add_argument("--taken-odds", default="")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--signal-probability", default="")
    parser.add_argument("--market-probability", default="")
    parser.add_argument("--no-vig-probability", default="")
    parser.add_argument("--edge-probability", default="")
    parser.add_argument("--model-name", default="")
    parser.add_argument("--strategy-name", default="")
    parser.add_argument("--confidence-label", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--status", default="observation")
    parser.add_argument("--result", default="unknown")
    parser.add_argument("--closing-odds", default="")
    parser.add_argument("--closing-source", default="")
    parser.add_argument("--notes", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.init:
            path = init_ledger(args.ledger)
            print(f"- Shadow ledger initialise: {path}")
        if args.add:
            entry = add_shadow_entry(args.ledger, **vars(args))
            print(f"- Signal shadow ajoute: {entry['shadow_id']}")
            print("- Observation seulement: aucune mise, aucun pick automatique.")
        if args.list:
            print_rows(read_ledger(args.ledger))
        if args.summary:
            print_summary(summarize_ledger(args.ledger))
        if args.export:
            path = export_ledger(args.ledger, args.export)
            print(f"- Export shadow ledger ecrit: {path}")
        if not any((args.init, args.add, args.list, args.summary, args.export)):
            print_summary(summarize_ledger(args.ledger))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
