import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List


ALLOWED_ACTIONS = {"collecter closing", "attendre resultat", "relancer evidence gate", "observation seulement", "refuser"}
REQUIRED_FORBIDDEN_ACTIONS = {"mise reelle", "pick automatique", "Telegram agressif"}
FORBIDDEN_TERMS = ["pari " + "conseille", "mise recommandee", "garanti", "rentable"]


def build_template() -> Dict[str, Any]:
    return {
        "event": {"match_date": "2026-06-01", "league": "EPL", "home_team": "Arsenal", "away_team": "Chelsea"},
        "analysis": {
            "data_sources": ["shadow ledger", "odds snapshots"],
            "model_signals": [],
            "market_signals": [],
            "xg_context": "non utilise",
            "clv_context": "CLV absente ou insuffisante",
            "evidence_context": "insufficient_evidence",
        },
        "observation": {"label": "observation shadow", "explanation": "Preuve insuffisante, suivi laboratoire uniquement."},
        "confidence": {"level": "faible", "reasons": ["sample insuffisant"], "sample_size": 0, "clv_coverage": 0.0},
        "risks": ["CLV absente", "sample faible"],
        "limits": ["pas de validation live suffisante", "aucune cote inventee"],
        "decision": {
            "status": "non valide",
            "allowed_actions": ["collecter closing", "attendre resultat", "relancer evidence gate", "observation seulement"],
            "forbidden_actions": ["mise reelle", "pick automatique", "Telegram agressif"],
        },
        "next_action": ["renseigner une closing odds reelle", "relancer shadow_clv_report.py"],
    }


def validate_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    for key in ["event", "analysis", "observation", "confidence", "risks", "limits", "decision", "next_action"]:
        if key not in data:
            errors.append(f"champ manquant: {key}")
    decision = data.get("decision") or {}
    allowed = set(decision.get("allowed_actions") or [])
    forbidden = set(decision.get("forbidden_actions") or [])
    bad_allowed = sorted(allowed - ALLOWED_ACTIONS)
    if bad_allowed:
        errors.append("actions autorisees invalides: " + ", ".join(bad_allowed))
    missing_forbidden = sorted(REQUIRED_FORBIDDEN_ACTIONS - forbidden)
    if missing_forbidden:
        errors.append("actions interdites obligatoires absentes: " + ", ".join(missing_forbidden))
    raw = json.dumps(data, ensure_ascii=False).lower()
    for term in FORBIDDEN_TERMS:
        if term in raw:
            errors.append(f"terme interdit detecte: {term}")
    return {"ok": not errors, "errors": errors}


def render_text(data: Dict[str, Any]) -> str:
    event = data.get("event") or {}
    observation = data.get("observation") or {}
    confidence = data.get("confidence") or {}
    decision = data.get("decision") or {}
    lines = [
        "Restitution Oracle",
        f"Evenement: {event.get('match_date')} - {event.get('league')} - {event.get('home_team')} vs {event.get('away_team')}",
        f"Observation: {observation.get('label')} - {observation.get('explanation')}",
        f"Confiance: {confidence.get('level')} (sample={confidence.get('sample_size')}, CLV coverage={confidence.get('clv_coverage')})",
        "Risques: " + "; ".join(str(item) for item in data.get("risks", [])),
        "Limites: " + "; ".join(str(item) for item in data.get("limits", [])),
        f"Decision: {decision.get('status')}",
        "Actions autorisees: " + "; ".join(decision.get("allowed_actions") or []),
        "Actions interdites: " + "; ".join(decision.get("forbidden_actions") or []),
        "Prochaine action: " + "; ".join(data.get("next_action") or []),
    ]
    return "\n".join(lines)


def write_template(output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_template(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(data: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Restitution Oracle</title></head><body><pre>"
        + html.escape(render_text(data))
        + "</pre></body></html>",
        encoding="utf-8",
    )
    return target


def load_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Schema de restitution prudent Oracle.")
    parser.add_argument("--template", default="")
    parser.add_argument("--render", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--validate", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.template:
        write_template(args.template)
        print(f"Template restitution ecrit: {args.template}")
    if args.validate:
        result = validate_schema(load_json(args.validate))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result["ok"]:
            return 1
    if args.render:
        text = render_text(load_json(args.render))
        if args.output:
            target = Path(args.output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            print(f"Preview restitution ecrite: {args.output}")
        else:
            print(text)
    if args.html:
        data = load_json(args.render) if args.render else build_template()
        write_html(data, args.html)
        print(f"HTML restitution ecrit: {args.html}")
    if not any([args.template, args.validate, args.render, args.html]):
        print(render_text(build_template()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
