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
VALID_RESULT = {"win", "loss", "push", "void", "unknown"}
CANDIDATE_IMPORT_COLUMNS = [
    "match_date",
    "league",
    "home_team",
    "away_team",
    "market_type",
    "side",
    "taken_odds",
    "bookmaker",
    "strategy_name",
    "reason",
    "confidence_label",
    "model_probability",
    "market_probability",
    "no_vig_probability",
    "edge_probability",
    "notes",
]


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


def _dedupe_key(row: Dict[str, Any]) -> tuple:
    return (
        str(row.get("match_date") or "").strip().lower(),
        str(row.get("league") or "").strip().lower(),
        str(row.get("home_team") or row.get("home") or "").strip().lower(),
        str(row.get("away_team") or row.get("away") or "").strip().lower(),
        str(row.get("market_type") or row.get("market") or "").strip().lower(),
        str(row.get("side") or "").strip().lower(),
        str(row.get("taken_odds") or "").strip().replace(",", "."),
    )


def _status_from_import(row: Dict[str, Any]) -> str:
    reason = str(row.get("reason") or "").lower()
    confidence = str(row.get("confidence_label") or "").lower()
    if "rejected" in reason or "refuse" in reason or "refus" in reason or "rejet" in reason:
        return "rejected"
    if "watchlist" in confidence:
        return "watchlist"
    return "observation"


def add_csv_entries(path: str, csv_path: str, allow_duplicates: bool = False) -> Dict[str, Any]:
    init_ledger(path)
    source = Path(csv_path)
    if not source.exists():
        raise FileNotFoundError(f"CSV observations shadow introuvable: {csv_path}")
    existing_rows = read_ledger(path)
    existing_keys = {_dedupe_key(row) for row in existing_rows}
    rows_read = 0
    added = 0
    duplicates = 0
    errors: List[str] = []
    with source.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader, start=2):
            rows_read += 1
            try:
                for required in ("match_date", "market_type", "side", "taken_odds"):
                    if not str(row.get(required) or "").strip():
                        raise ValueError(f"{required} obligatoire")
                key = _dedupe_key(row)
                if key in existing_keys and not allow_duplicates:
                    duplicates += 1
                    continue
                entry = add_shadow_entry(
                    path,
                    match_date=row.get("match_date"),
                    league=row.get("league"),
                    home_team=row.get("home_team"),
                    away_team=row.get("away_team"),
                    market_type=row.get("market_type"),
                    side=row.get("side"),
                    taken_odds=row.get("taken_odds"),
                    bookmaker=row.get("bookmaker"),
                    strategy_name=row.get("strategy_name"),
                    reason=row.get("reason"),
                    confidence_label=row.get("confidence_label"),
                    signal_probability=row.get("model_probability"),
                    market_probability=row.get("market_probability"),
                    no_vig_probability=row.get("no_vig_probability"),
                    edge_probability=row.get("edge_probability"),
                    notes=row.get("notes"),
                    status=_status_from_import(row),
                )
                existing_keys.add(_dedupe_key(entry))
                added += 1
            except Exception as exc:
                errors.append(f"Ligne {idx}: {exc}")
    return {
        "ledger": path,
        "csv_path": csv_path,
        "rows_read": rows_read,
        "rows_added": added,
        "duplicates_ignored": duplicates,
        "errors": errors,
        "lab_only": True,
        "can_influence_picks": False,
    }


def pending_closing(path: str = DEFAULT_LEDGER) -> List[Dict[str, str]]:
    return [row for row in read_ledger(path) if not str(row.get("closing_odds") or "").strip()]


def pending_results(path: str = DEFAULT_LEDGER) -> List[Dict[str, str]]:
    return [row for row in read_ledger(path) if str(row.get("result") or "unknown").lower() == "unknown"]


def set_result(path: str, shadow_id: str, result: str) -> Dict[str, Any]:
    result = str(result or "").strip().lower()
    if result not in VALID_RESULT:
        raise ValueError(f"result invalide: {result}")
    rows = read_ledger(path)
    updated = False
    for row in rows:
        if row.get("shadow_id") == shadow_id:
            row["result"] = result
            if result in {"win", "loss", "push", "void"}:
                row["status"] = "settled"
            updated = True
            break
    if not updated:
        raise ValueError(f"shadow_id introuvable: {shadow_id}")
    write_ledger(rows, path)
    return {"shadow_id": shadow_id, "result": result, "updated": True}


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


def print_import_summary(summary: Dict[str, Any]) -> None:
    print("Import CSV observations shadow Oracle Bot")
    print(f"- CSV: {summary.get('csv_path')}")
    print(f"- Lignes lues: {summary.get('rows_read')}")
    print(f"- Lignes ajoutees: {summary.get('rows_added')}")
    print(f"- Doublons ignores: {summary.get('duplicates_ignored')}")
    print(f"- Erreurs: {len(summary.get('errors') or [])}")
    for error in summary.get("errors") or []:
        print(f"  - {error}")
    print("- Mode shadow : observation seulement, aucune mise conseillee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Journal local des signaux shadow Oracle Bot, sans recommandation de mise.")
    parser.add_argument("--ledger", default=DEFAULT_LEDGER, help="Chemin du ledger CSV, par defaut reports/shadow_ledger.csv")
    parser.add_argument("--init", action="store_true", help="Initialise le ledger")
    parser.add_argument("--add", action="store_true", help="Ajoute un signal shadow")
    parser.add_argument("--add-csv", default="", help="Ajoute plusieurs observations depuis un CSV")
    parser.add_argument("--allow-duplicates", action="store_true", help="Autorise les doublons lors de --add-csv")
    parser.add_argument("--list", action="store_true", help="Liste les signaux shadow")
    parser.add_argument("--summary", action="store_true", help="Resume le ledger")
    parser.add_argument("--export", default="", help="Exporte le ledger vers un CSV dans reports/")
    parser.add_argument("--pending-closing", action="store_true", help="Liste les observations sans closing odds")
    parser.add_argument("--pending-results", action="store_true", help="Liste les observations sans resultat")
    parser.add_argument("--set-result", action="store_true", help="Met a jour le resultat d'une observation")
    parser.add_argument("--shadow-id", default="", help="shadow_id pour --set-result")
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
        if args.add_csv:
            print_import_summary(add_csv_entries(args.ledger, args.add_csv, allow_duplicates=args.allow_duplicates))
        if args.list:
            print_rows(read_ledger(args.ledger))
        if args.pending_closing:
            print_rows(pending_closing(args.ledger))
        if args.pending_results:
            print_rows(pending_results(args.ledger))
        if args.set_result:
            updated = set_result(args.ledger, args.shadow_id, args.result)
            print(f"- Resultat mis a jour: {updated['shadow_id']} -> {updated['result']}")
            print("- Mode shadow : observation seulement, aucune mise conseillee.")
        if args.summary:
            print_summary(summarize_ledger(args.ledger))
        if args.export:
            path = export_ledger(args.ledger, args.export)
            print(f"- Export shadow ledger ecrit: {path}")
        if not any((args.init, args.add, args.add_csv, args.list, args.summary, args.export, args.pending_closing, args.pending_results, args.set_result)):
            print_summary(summarize_ledger(args.ledger))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
