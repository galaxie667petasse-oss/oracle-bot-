import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


CATALOG: List[Dict[str, Any]] = [
    {
        "name": "Manual odds snapshots",
        "type": "manual_csv",
        "coverage": "live_manual",
        "cost": "gratuit",
        "network_required": False,
        "can_provide_taken_odds": True,
        "can_provide_near_close": True,
        "can_provide_historical_closing": False,
        "reliability": "controle humain requis",
        "risk": "saisie manuelle, sample lent",
        "recommended_use": "capture shadow quotidienne",
    },
    {
        "name": "The Odds API",
        "type": "api_optional",
        "coverage": "live_and_some_historical_paid",
        "cost": "free limited / paid historical",
        "network_required": True,
        "can_provide_taken_odds": True,
        "can_provide_near_close": True,
        "can_provide_historical_closing": "paid_or_plan_dependent",
        "reliability": "bonne si timestamps et bookmaker stables",
        "risk": "credits limites, historique souvent payant",
        "recommended_use": "near-close future si cle explicite",
    },
    {
        "name": "API-Football",
        "type": "api_optional",
        "coverage": "fixtures_results_odds_plan_dependent",
        "cost": "free limited / paid tiers",
        "network_required": True,
        "can_provide_taken_odds": "plan_dependent",
        "can_provide_near_close": "plan_dependent",
        "can_provide_historical_closing": "uncertain",
        "reliability": "utile pour resultats et fixtures",
        "risk": "odds closing pas garanties selon plan",
        "recommended_use": "resultats et controle fixtures",
    },
    {
        "name": "Football-Data CSV",
        "type": "local_csv",
        "coverage": "historique europeen",
        "cost": "gratuit",
        "network_required": False,
        "can_provide_taken_odds": True,
        "can_provide_near_close": False,
        "can_provide_historical_closing": "seulement si colonnes closing decimales documentees",
        "reliability": "bonne pour resultats, closing a verifier",
        "risk": "colonnes C_* peuvent ne pas etre des cotes",
        "recommended_use": "schema detector avant import CLV",
    },
    {
        "name": "Betclic manuel",
        "type": "manual_source",
        "coverage": "matchday humain",
        "cost": "gratuit",
        "network_required": False,
        "can_provide_taken_odds": True,
        "can_provide_near_close": True,
        "can_provide_historical_closing": False,
        "reliability": "depend de la discipline de capture",
        "risk": "pas d'historique massif",
        "recommended_use": "shadow loop juin",
    },
    {
        "name": "OddsPortal / Kaggle / vendor historical",
        "type": "external_dataset",
        "coverage": "historique selon source",
        "cost": "variable",
        "network_required": False,
        "can_provide_taken_odds": "source_dependent",
        "can_provide_near_close": "source_dependent",
        "can_provide_historical_closing": True,
        "reliability": "a auditer strictement",
        "risk": "licence, mapping equipes, timestamps, biais de selection",
        "recommended_use": "accelerer preuve historique si schema fiable",
    },
]


def ensure_reports_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le catalogue de preuves ne doit pas etre ecrit dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def build_catalog() -> Dict[str, Any]:
    recommended = [
        "Verifier tout CSV historique avec historical_odds_schema_detector.py",
        "Ne calculer la CLV que si opening et closing odds decimales sont plausibles",
        "Utiliser le shadow mode pour la preuve live",
        "Conserver les API en option explicite avec --allow-network",
    ]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sources": CATALOG,
        "summary": {
            "sources_count": len(CATALOG),
            "offline_sources": sum(1 for item in CATALOG if not item["network_required"]),
            "network_optional_sources": sum(1 for item in CATALOG if item["network_required"]),
            "historical_closing_candidates": [
                item["name"] for item in CATALOG if item["can_provide_historical_closing"] not in {False, "uncertain"}
            ],
        },
        "recommended_next_steps": recommended,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = ensure_reports_path(output)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('name')))}</td>"
        f"<td>{html.escape(str(item.get('type')))}</td>"
        f"<td>{html.escape(str(item.get('coverage')))}</td>"
        f"<td>{html.escape(str(item.get('can_provide_historical_closing')))}</td>"
        f"<td>{html.escape(str(item.get('risk')))}</td>"
        "</tr>"
        for item in report.get("sources") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body>"
        "<h1>Catalogue preuves externes</h1>"
        "<p>Laboratoire local: aucune mise, aucun signal automatique.</p>"
        "<table border='1'><tr><th>Source</th><th>Type</th><th>Coverage</th><th>Closing historique</th><th>Risque</th></tr>"
        + rows
        + "</table></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Catalogue preuves externes Oracle")
    print(f"- Sources: {report['summary']['sources_count']}")
    print(f"- Sources offline: {report['summary']['offline_sources']}")
    print(f"- Sources reseau optionnel: {report['summary']['network_optional_sources']}")
    for step in report.get("recommended_next_steps") or []:
        print(f"- Action: {step}")
    print("- Observation seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Catalogue local des sources de preuve externes.")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_catalog()
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
