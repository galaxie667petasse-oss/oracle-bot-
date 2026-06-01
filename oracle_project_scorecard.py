import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict


SCORE_KEYS = [
    "sources de donnees",
    "collecte & nettoyage",
    "base & versioning",
    "moteur de signaux",
    "LLM analyste",
    "restitution",
    "boucle de progression",
    "securite",
    "preuve betting reelle",
    "readiness juin",
]


def _exists(path: str) -> bool:
    return Path(path).exists()


def _load_json(path: str) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def build_scorecard(reports_dir: str = "reports") -> Dict[str, Any]:
    reports = Path(reports_dir)
    shadow = _load_json(str(reports / "shadow_clv_report.json"))
    evidence = _load_json(str(reports / "evidence_gate.json"))
    big5 = _load_json(str(reports / "big5_xg_summary.json"))
    clv_coverage = float(shadow.get("clv_coverage") or 0)
    sample = int(float(shadow.get("sample_size") or shadow.get("signals_total") or 0))
    clv_mean = shadow.get("clv_mean")
    clv_mean_value = float(clv_mean) if clv_mean not in (None, "") else 0.0
    big5_global = big5.get("global") or {}
    scores = {
        "sources de donnees": 85 if _exists("multi_league_xg_aggregator.py") and _exists("odds_snapshot_store.py") else 55,
        "collecte & nettoyage": 88 if _exists("odds_intake_audit.py") and _exists("xg_dataset_quality.py") else 60,
        "base & versioning": 82 if _exists("project_audit.py") else 50,
        "moteur de signaux": 86 if _exists("evidence_gate.py") and _exists("benchmark_governance.py") else 55,
        "LLM analyste": 45 if _exists("llm_analyst_contract.py") else 15,
        "restitution": 78 if _exists("dashboard_builder.py") and _exists("restitution_schema.py") else 55,
        "boucle de progression": 65 if _exists("progress_loop.py") else 25,
        "securite": 90 if _exists(".gitignore") and _exists("project_audit.py") else 45,
        "preuve betting reelle": 20,
        "readiness juin": 82 if _exists("shadow_workflow.py") and _exists("oracle_ops.py") else 45,
    }
    if sample >= 1000 and clv_coverage >= 80 and clv_mean_value > 0:
        scores["preuve betting reelle"] = 55
    elif sample > 0 or clv_coverage > 0:
        scores["preuve betting reelle"] = 30
    reasons = {
        key: {
            "score": value,
            "reason": _reason_for(key, value, sample, clv_coverage, big5_global, evidence),
            "risks": _risks_for(key),
            "next_actions": _next_for(key),
        }
        for key, value in scores.items()
    }
    global_score = round(sum(scores.values()) / len(scores), 2)
    return {
        "global_score": global_score,
        "scores": reasons,
        "shadow_sample": sample,
        "shadow_clv_coverage": clv_coverage,
        "evidence_status": evidence.get("global_status"),
        "big5_complete": big5_global.get("ready_for_big5_conclusion"),
        "robust_candidates": 0,
        "lab_only": True,
        "can_influence_picks": False,
        "conclusion": "Projet structure pour observer et mesurer; preuve betting reelle encore basse tant que CLV/sample restent insuffisants.",
    }


def _reason_for(key: str, score: int, sample: int, clv_coverage: float, big5: Dict[str, Any], evidence: Dict[str, Any]) -> str:
    if key == "preuve betting reelle":
        return f"sample shadow={sample}, coverage CLV={clv_coverage}%; pas de promotion sans sample >=1000 et CLV fiable."
    if key == "LLM analyste":
        return "Contrat cree, mais le LLM reste explicatif et non branche comme source de verite."
    if key == "sources de donnees":
        return f"Big 5 complet={big5.get('ready_for_big5_conclusion')}; odds lab disponible."
    if key == "moteur de signaux":
        return f"Evidence gate={evidence.get('global_status')}; gouvernance prudente."
    return "Composant present et auditable localement." if score >= 70 else "Composant partiel ou en laboratoire."


def _risks_for(key: str):
    common = ["surinterpretation", "sample insuffisant"]
    if key == "preuve betting reelle":
        return ["CLV absente ou incomplete", "sample < 1000", "resultats live insuffisants"]
    if key == "LLM analyste":
        return ["hallucination", "ton trop affirmatif", "invention de donnees"]
    return common


def _next_for(key: str):
    if key == "preuve betting reelle":
        return ["collecter observations shadow", "renseigner near-close reelles", "relancer evidence gate"]
    if key == "LLM analyste":
        return ["valider le contrat", "tester le rendu preview", "bloquer toute sortie trop agressive"]
    return ["continuer audits locaux", "documenter les ecarts"]


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    parts = ["<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Scorecard Oracle</title></head><body>"]
    parts.append(f"<h1>Scorecard Oracle</h1><p>Score global: {report['global_score']}</p>")
    for name, item in report["scores"].items():
        parts.append(f"<section><h2>{html.escape(name)}</h2><pre>{html.escape(json.dumps(item, ensure_ascii=False, indent=2))}</pre></section>")
    parts.append("</body></html>")
    target.write_text("\n".join(parts), encoding="utf-8")
    return target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Scorecard maturite Oracle.")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = build_scorecard(args.reports_dir)
    print("Scorecard projet Oracle")
    print(f"- Score global: {report['global_score']}")
    print(f"- Preuve betting reelle: {report['scores']['preuve betting reelle']['score']}")
    print("- Statut: laboratoire prudent, aucune mise.")
    if args.output:
        write_json(report, args.output)
        print(f"JSON scorecard ecrit: {args.output}")
    if args.html:
        write_html(report, args.html)
        print(f"HTML scorecard ecrit: {args.html}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
