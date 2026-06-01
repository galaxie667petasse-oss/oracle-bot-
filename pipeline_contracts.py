import argparse
import csv
import html
import json
import math
from pathlib import Path
from typing import Any, Dict, List


def _contract(name: str, required: List[str], optional: List[str], rules: List[str], example: Dict[str, Any], rejected: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "required_columns": required,
        "optional_columns": optional,
        "types": {column: "string" for column in required + optional},
        "validation_rules": rules,
        "minimal_example": example,
        "rejected_example": rejected,
        "error_message_fr": f"Contrat {name}: colonnes obligatoires absentes ou valeurs non plausibles.",
    }


CONTRACTS: Dict[str, Dict[str, Any]] = {
    "match_source": _contract(
        "match_source",
        ["match_date", "league", "home_team", "away_team"],
        ["source", "source_event_id", "season", "home_score", "away_score"],
        ["date valide", "equipes non vides", "source tracee si disponible"],
        {"match_date": "2026-06-01", "league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea"},
        {"match_date": "", "league": "EPL", "home_team": "", "away_team": "Chelsea"},
    ),
    "odds_snapshot": _contract(
        "odds_snapshot",
        ["snapshot_id", "captured_at", "source", "match_date", "home_team", "away_team", "market_type", "side", "odds", "is_near_close"],
        ["league", "kickoff_time", "bookmaker", "normalized_home", "normalized_away", "validation_status"],
        ["odds decimales > 1.01 et < 100", "ne jamais accepter une probabilite 0-1 comme cote", "near-close separe de taken odds"],
        {"snapshot_id": "odds_1", "captured_at": "2026-06-01T10:00:00", "source": "manual", "match_date": "2026-06-01", "home_team": "A", "away_team": "B", "market_type": "h2h", "side": "home", "odds": "2.10", "is_near_close": "False"},
        {"snapshot_id": "odds_bad", "captured_at": "2026-06-01", "source": "manual", "match_date": "2026-06-01", "home_team": "A", "away_team": "B", "market_type": "h2h", "side": "home", "odds": "0.52", "is_near_close": "False"},
    ),
    "feature_row": _contract(
        "feature_row",
        ["date", "home_team", "away_team", "market_type", "odds"],
        ["no_vig_probability", "elo_diff", "rolling_xg_avg3", "rolling_xg_avg5"],
        ["features pre-match uniquement pour prediction", "pas de fuite post-match"],
        {"date": "2024-01-01", "home_team": "A", "away_team": "B", "market_type": "h2h", "odds": "2.0"},
        {"date": "2024-01-01", "home_team": "A", "away_team": "B", "market_type": "h2h", "odds": "0.8"},
    ),
    "shadow_ledger": _contract(
        "shadow_ledger",
        ["shadow_id", "match_date", "league", "home_team", "away_team", "market_type", "side", "taken_odds", "status"],
        ["closing_odds", "clv_percent", "result", "strategy_name", "notes"],
        ["taken_odds decimales plausibles", "closing_odds obligatoire seulement pour CLV", "statut prudent"],
        {"shadow_id": "sh_1", "match_date": "2026-06-01", "league": "EPL", "home_team": "A", "away_team": "B", "market_type": "h2h", "side": "home", "taken_odds": "2.10", "status": "observation"},
        {"shadow_id": "sh_bad", "match_date": "2026-06-01", "league": "EPL", "home_team": "A", "away_team": "B", "market_type": "h2h", "side": "home", "taken_odds": "1.00", "status": "observation"},
    ),
    "closing_import": _contract(
        "closing_import",
        ["shadow_id", "closing_odds", "closing_source"],
        ["notes"],
        ["closing_odds decimales > 1.01", "ne jamais inventer une closing absente"],
        {"shadow_id": "sh_1", "closing_odds": "2.00", "closing_source": "manual_near_close"},
        {"shadow_id": "sh_1", "closing_odds": "", "closing_source": "unknown"},
    ),
    "result_import": _contract(
        "result_import",
        ["shadow_id", "result"],
        ["notes"],
        ["result dans win/loss/push/void/unknown"],
        {"shadow_id": "sh_1", "result": "win"},
        {"shadow_id": "sh_1", "result": "maybe"},
    ),
    "signal_evaluation": _contract(
        "signal_evaluation",
        ["model_name", "sample_size", "roi", "clv_available", "promotion_allowed"],
        ["brier_delta", "logloss_delta", "blockers"],
        ["sample >= 1000 pour analyse forte", "CLV positive fiable obligatoire"],
        {"model_name": "xg_lab", "sample_size": "1200", "roi": "0.01", "clv_available": "true", "promotion_allowed": "false"},
        {"model_name": "xg_lab", "sample_size": "50", "roi": "0.10", "clv_available": "false", "promotion_allowed": "true"},
    ),
    "llm_analyst_input": _contract(
        "llm_analyst_input",
        ["event", "market", "measured_signals", "governance", "data_quality"],
        ["allowed_output_labels"],
        ["le LLM explique seulement", "aucune cote inventee", "aucune decision plus agressive qu'evidence_gate"],
        {"event": "{}", "market": "{}", "measured_signals": "{}", "governance": "{}", "data_quality": "{}"},
        {"event": "{}", "market": "{}", "measured_signals": "edge invente", "governance": "", "data_quality": "{}"},
    ),
    "restitution_output": _contract(
        "restitution_output",
        ["event", "analysis", "observation", "confidence", "risks", "limits", "decision", "next_action"],
        [],
        ["actions autorisees limitees", "actions interdites visibles", "mots interdits absents"],
        {"event": "{}", "analysis": "{}", "observation": "{}", "confidence": "{}", "risks": "[]", "limits": "[]", "decision": "{}", "next_action": "[]"},
        {"event": "{}", "analysis": "{}", "observation": "agressive", "confidence": "{}", "risks": "[]", "limits": "[]", "decision": "{}", "next_action": "[]"},
    ),
    "evidence_gate": _contract(
        "evidence_gate",
        ["global_status", "blockers", "required_next_steps"],
        ["strengths", "quality_status", "shadow_sample"],
        ["jamais ready_for_betting", "sample faible bloque", "CLV absente bloque"],
        {"global_status": "insufficient_evidence", "blockers": "sample < 1000", "required_next_steps": "collecter"},
        {"global_status": "ready_for_betting", "blockers": "", "required_next_steps": ""},
    ),
}


def _as_float(value: Any) -> float:
    text = str(value or "").strip().replace(",", ".")
    number = float(text)
    if not math.isfinite(number):
        raise ValueError
    return number


def _validate_row(contract_name: str, row: Dict[str, Any], index: int) -> List[str]:
    errors: List[str] = []
    contract = CONTRACTS[contract_name]
    for column in contract["required_columns"]:
        if str(row.get(column, "")).strip() == "":
            errors.append(f"ligne {index}: colonne obligatoire absente ou vide: {column}")
    odds_columns = ["odds", "taken_odds", "closing_odds"]
    for column in odds_columns:
        if column not in row or str(row.get(column, "")).strip() == "":
            continue
        try:
            value = _as_float(row.get(column))
            if value <= 1.01 or value >= 100:
                errors.append(f"ligne {index}: {column} n'est pas une cote decimale plausible")
        except Exception:
            errors.append(f"ligne {index}: {column} non numerique")
    if contract_name == "result_import" and row.get("result") not in {"win", "loss", "push", "void", "unknown"}:
        errors.append(f"ligne {index}: result invalide")
    if contract_name == "evidence_gate" and str(row.get("global_status", "")).strip() == "ready_for_betting":
        errors.append(f"ligne {index}: statut evidence interdit")
    return errors


def validate_csv(contract_name: str, csv_path: str) -> Dict[str, Any]:
    if contract_name not in CONTRACTS:
        raise ValueError(f"Contrat inconnu: {contract_name}")
    path = Path(csv_path)
    if not path.exists():
        return {"ok": False, "errors": [f"CSV absent: {csv_path}"], "rows": 0}
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        headers = reader.fieldnames or []
        missing = [column for column in CONTRACTS[contract_name]["required_columns"] if column not in headers]
        errors = [f"colonne obligatoire absente: {column}" for column in missing]
        rows = 0
        for rows, row in enumerate(reader, start=1):
            errors.extend(_validate_row(contract_name, row, rows))
    return {"ok": not errors, "contract": contract_name, "csv": csv_path, "rows": rows, "errors": errors}


def write_json(output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"contracts": CONTRACTS}, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    parts = ["<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Contrats pipeline</title></head><body><h1>Contrats pipeline Oracle</h1>"]
    for key, contract in CONTRACTS.items():
        parts.append(f"<section><h2>{html.escape(key)}</h2><pre>{html.escape(json.dumps(contract, ensure_ascii=False, indent=2))}</pre></section>")
    parts.append("</body></html>")
    target.write_text("\n".join(parts), encoding="utf-8")
    return target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Contrats de donnees du pipeline Oracle.")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--show", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--csv", default="")
    parser.add_argument("--json", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list or not any([args.show, args.validate, args.json, args.html]):
        print("Contrats disponibles")
        for name in CONTRACTS:
            print(f"- {name}")
    if args.show:
        if args.show not in CONTRACTS:
            print(f"Contrat inconnu: {args.show}")
            return 1
        print(json.dumps(CONTRACTS[args.show], ensure_ascii=False, indent=2))
    if args.validate:
        result = validate_csv(args.validate, args.csv)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            return 1
    if args.json:
        write_json(args.json)
        print(f"JSON contrats ecrit: {args.json}")
    if args.html:
        write_html(args.html)
        print(f"HTML contrats ecrit: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
