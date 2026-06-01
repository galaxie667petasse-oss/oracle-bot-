import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


ALLOWED_OUTPUT_LABELS = ["refus", "observation shadow", "watchlist", "non valide", "analyse approfondie requise"]
FORBIDDEN_TERMS = ["pari " + "conseille", "mise recommandee", "garanti", "rentable"]


def build_template() -> Dict[str, Any]:
    return {
        "event": {
            "match_date": "2026-06-01",
            "league": "EPL",
            "home_team": "Arsenal",
            "away_team": "Chelsea",
        },
        "market": {
            "market_type": "h2h",
            "side": "home",
            "taken_odds": 2.10,
            "closing_odds": None,
        },
        "measured_signals": {
            "model_probability": None,
            "market_probability": None,
            "no_vig_probability": None,
            "edge_probability": None,
            "clv_percent": None,
            "roi_shadow": None,
            "sample_size": 0,
            "brier_delta": None,
            "logloss_delta": None,
        },
        "governance": {
            "evidence_status": "insufficient_evidence",
            "decision_policy": "non valide",
            "blockers": ["CLV absente ou insuffisante.", "Sample insuffisant."],
            "warnings": ["Le LLM explique uniquement les mesures fournies."],
        },
        "data_quality": {
            "source_quality": "laboratoire",
            "missing_fields": ["closing_odds"],
            "leak_risk": "controle requis",
        },
        "allowed_output_labels": ALLOWED_OUTPUT_LABELS,
    }


def validate_input(data: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    for section in ["event", "market", "measured_signals", "governance", "data_quality"]:
        if not isinstance(data.get(section), dict):
            errors.append(f"section manquante ou invalide: {section}")
    raw = json.dumps(data, ensure_ascii=False).lower()
    for term in FORBIDDEN_TERMS:
        if term in raw:
            errors.append(f"terme interdit detecte: {term}")
    signals = data.get("measured_signals") or {}
    governance = data.get("governance") or {}
    sample_size = int(float(signals.get("sample_size") or 0))
    if signals.get("clv_percent") in ("", None):
        warnings.append("CLV absente ou insuffisante.")
    if sample_size < 1000:
        warnings.append("Sample insuffisant.")
    evidence_status = governance.get("evidence_status")
    max_label = "analyse approfondie requise" if evidence_status == "ready_for_deep_review" else "non valide"
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "max_allowed_label": max_label,
        "llm_is_source_of_truth": False,
        "can_calculate_edge": False,
        "can_override_evidence_gate": False,
    }


def render_preview(data: Dict[str, Any]) -> str:
    validation = validate_input(data)
    event = data.get("event") or {}
    market = data.get("market") or {}
    signals = data.get("measured_signals") or {}
    governance = data.get("governance") or {}
    blockers = governance.get("blockers") or validation["warnings"] or ["preuve insuffisante"]
    lines = [
        "Oracle LLM Analyst - Preview",
        f"Decision prudente: {validation['max_allowed_label']}",
        f"Evenement: {event.get('match_date')} - {event.get('league')} - {event.get('home_team')} vs {event.get('away_team')}",
        f"Marche: {market.get('market_type')} / {market.get('side')}",
        "Donnees utilisees: uniquement les mesures fournies par les modules.",
        f"Signaux mesures: sample={signals.get('sample_size')}, CLV={signals.get('clv_percent')}, ROI shadow={signals.get('roi_shadow')}",
        "Risques: " + "; ".join(str(item) for item in blockers),
        "Limites: le LLM ne calcule pas l'edge et ne cree aucune cote.",
        "Prochaine action: collecter closing/resultats puis relancer evidence gate.",
        "Observation shadow uniquement. Aucune mise conseillee.",
    ]
    return "\n".join(lines)


def write_template(output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_template(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Contrat du futur LLM analyste Oracle, sans appel LLM.")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--template-json", default="")
    parser.add_argument("--validate-input", default="")
    parser.add_argument("--render-preview", default="")
    parser.add_argument("--output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.show or not any([args.template_json, args.validate_input, args.render_preview]):
        print("Contrat LLM analyste")
        print("- Le LLM n'est pas source de verite.")
        print("- Le LLM explique les mesures, sans inventer de cote ni changer evidence gate.")
        print("- Labels autorises: " + ", ".join(ALLOWED_OUTPUT_LABELS))
    if args.template_json:
        write_template(args.template_json)
        print(f"Template LLM ecrit: {args.template_json}")
    if args.validate_input:
        result = validate_input(load_json(args.validate_input))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            return 1
    if args.render_preview:
        text = render_preview(load_json(args.render_preview))
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(f"Preview LLM ecrite: {args.output}")
        else:
            print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
