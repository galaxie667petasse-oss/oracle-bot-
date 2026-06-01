import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ARCHITECTURE_BLOCKS = [
    {
        "id": "data_sources",
        "name": "Sources de donnees",
        "role": "Regrouper les sources brutes et les entrees manuelles sans les confondre avec une preuve.",
        "inputs": ["matchs", "equipes", "joueurs", "cotes", "calendrier", "forme recente", "actualites", "xG", "resultats", "near-close odds"],
        "outputs": ["CSV sources", "snapshots de cotes", "ledger shadow", "exports Understat"],
        "modules": ["understat_probe.py", "manual_odds_import.py", "api_football_odds_adapter.py", "the_odds_api_adapter.py", "shadow_ledger.py", "results_manual_import.py"],
        "files": ["data/MATCHES.csv", "data/features_modern.csv", "reports/odds_snapshots.csv", "reports/shadow_ledger.csv", "external_data/understat_probe"],
        "status": "partiel",
        "risks": ["closing odds historiques non fiables dans data/MATCHES.csv", "API optionnelles non configurees", "donnees live non garanties"],
        "next_actions": ["collecter snapshots manuels", "capturer near-close reelles", "garder reports/ hors Git"],
    },
    {
        "id": "collection_cleaning",
        "name": "Collecte & nettoyage",
        "role": "Normaliser, controler et refuser les donnees douteuses avant tout calcul.",
        "inputs": ["CSV sources", "exports xG", "snapshots odds", "alias equipes"],
        "outputs": ["donnees validees", "rapports qualite", "rejets explicites"],
        "modules": ["xgabora_dataset_import.py", "understat_probe.py", "external_xg_lab.py", "external_xg_features.py", "team_name_normalizer.py", "odds_normalizer.py", "odds_source_quality_report.py", "odds_intake_audit.py"],
        "files": ["reports/odds_source_quality.json", "reports/odds_intake_audit.json", "reports/*_join_diagnostics.json"],
        "status": "pret",
        "risks": ["alias ambigus", "jointure fragile", "valeurs de cotes non plausibles"],
        "next_actions": ["auditer chaque nouveau CSV", "journaliser les rejets", "ne jamais corriger silencieusement"],
    },
    {
        "id": "database_versioning",
        "name": "Base de donnees & versioning",
        "role": "Proteger les fichiers sensibles, tracer les sources et separer donnees locales de Git.",
        "inputs": ["features protegees", "ledger shadow", "snapshots", "rapports locaux"],
        "outputs": ["etat auditable", "historique Git propre", "rapports ignores"],
        "modules": ["project_audit.py", "report_runner.py", "odds_snapshot_store.py"],
        "files": ["oracle_db.json", "data/features_modern.csv", "model_registry.json", ".gitignore", "reports/", "external_data/"],
        "status": "pret",
        "risks": ["committer des rapports locaux", "modifier data/ par erreur", "confondre model_registry et preuve"],
        "next_actions": ["lancer project_audit.py", "verifier git status", "ne jamais ecrire les previews dans data/"],
    },
    {
        "id": "signal_engine",
        "name": "Moteur de signaux",
        "role": "Mesurer pricing, modeles, calibration, CLV et evidence gate avec des regles prudentes.",
        "inputs": ["features", "pricing", "xG rolling", "Elo", "forme", "CLV", "resultats"],
        "outputs": ["scores", "backtests", "gouvernance", "refus prudent"],
        "modules": ["pricing.py", "feature_builder.py", "model_trainer.py", "backtest_evaluator.py", "calibration_report.py", "statistical_validation.py", "clv_analysis.py", "benchmark_governance.py", "decision_policy.py", "evidence_gate.py"],
        "files": ["reports/benchmark_summary.json", "reports/evidence_gate.json", "reports/clv_partial_report.json"],
        "status": "pret",
        "risks": ["sample insuffisant", "CLV absente", "multiple testing", "seuil choisi sur test"],
        "next_actions": ["collecter CLV shadow", "respecter evidence gate", "ne pas promouvoir sans sample >= 1000"],
    },
    {
        "id": "llm_analyst",
        "name": "LLM analyste",
        "role": "Expliquer des mesures fournies sans devenir source de verite ni changer la decision prudente.",
        "inputs": ["signaux mesures", "blockers", "qualite donnees", "decision evidence gate"],
        "outputs": ["explication standardisee", "risques", "limites", "prochaine action"],
        "modules": ["llm_analyst_contract.py", "shadow_message_formatter.py"],
        "files": ["reports/llm_analyst_input_template.json", "reports/shadow_messages_preview.txt"],
        "status": "laboratoire",
        "risks": ["hallucination", "ton trop agressif", "invention de cote"],
        "next_actions": ["valider le contrat", "bloquer les mots interdits", "garder le LLM explicatif seulement"],
    },
    {
        "id": "restitution",
        "name": "Restitution",
        "role": "Presenter JSON, HTML et texte prive sans envoi en gardant la prudence visible.",
        "inputs": ["rapports", "evidence gate", "shadow report", "scorecard"],
        "outputs": ["dashboard", "JSON", "HTML", "message preview"],
        "modules": ["dashboard_builder.py", "report_runner.py", "shadow_clv_report.py", "restitution_schema.py"],
        "files": ["reports/index.html", "reports/summary.json", "reports/restitution_preview.txt"],
        "status": "pret",
        "risks": ["confusion entre observation et action", "rapport incomplet", "lecture hors contexte"],
        "next_actions": ["standardiser les sorties", "afficher les blockers", "rappeler aucune mise"],
    },
    {
        "id": "progress_loop",
        "name": "Boucle de progression",
        "role": "Collecter, tester, mesurer, corriger et documenter sans casser les garde-fous.",
        "inputs": ["erreurs", "rapports", "audits", "notes de runbook"],
        "outputs": ["journal de progression", "actions suivantes", "ameliorations prudentes"],
        "modules": ["progress_loop.py", "oracle_ops.py", "agent_orchestrator_dryrun.py"],
        "files": ["reports/progress_loop.csv", "docs/june_shadow_runbook.md"],
        "status": "laboratoire",
        "risks": ["iteration non tracee", "surinterpretation d'un petit sample"],
        "next_actions": ["tenir le journal", "relire evidence gate", "corriger avant d'ajouter de la complexite"],
    },
]


def build_architecture_map(root: Path = Path("."), check_files: bool = False) -> Dict[str, Any]:
    blocks: List[Dict[str, Any]] = []
    for block in ARCHITECTURE_BLOCKS:
        item = dict(block)
        if check_files:
            item["file_status"] = {
                file_name: (root / file_name).exists() if not file_name.endswith("/") else (root / file_name.rstrip("/")).exists()
                for file_name in item["files"]
                if "*" not in file_name
            }
            item["module_status"] = {module: (root / module).exists() for module in item["modules"]}
        blocks.append(item)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "canonical_rule": "Les donnees alimentent, les modules mesurent, l'agent orchestre, le LLM explique.",
        "llm_is_source_of_truth": False,
        "lab_only": True,
        "can_influence_picks": False,
        "blocks": blocks,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    parts = ["<!doctype html><html lang='fr'><head><meta charset='utf-8'><title>Architecture Oracle</title></head><body>"]
    parts.append("<h1>Architecture canonique Oracle Football Bot</h1>")
    parts.append(f"<p>{html.escape(report['canonical_rule'])}</p>")
    for block in report["blocks"]:
        parts.append(f"<section><h2>{html.escape(block['name'])}</h2>")
        parts.append(f"<p><strong>Role:</strong> {html.escape(block['role'])}</p>")
        parts.append(f"<p><strong>Statut:</strong> {html.escape(block['status'])}</p>")
        parts.append("<pre>" + html.escape(json.dumps({
            "modules": block.get("modules"),
            "files": block.get("files"),
            "risks": block.get("risks"),
            "next_actions": block.get("next_actions"),
        }, ensure_ascii=False, indent=2)) + "</pre></section>")
    parts.append("</body></html>")
    target.write_text("\n".join(parts), encoding="utf-8")
    return target


def print_show(report: Dict[str, Any]) -> None:
    print("Architecture canonique Oracle Football Bot")
    print(f"- Regle: {report['canonical_rule']}")
    for block in report["blocks"]:
        print(f"- {block['name']} [{block['status']}]: {block['role']}")
    print("- Mode laboratoire: aucune mise, aucun Telegram, aucun Railway.")


def print_status(report: Dict[str, Any]) -> None:
    print("Statut architecture canonique")
    for block in report["blocks"]:
        modules = block.get("module_status") or {}
        missing = [name for name, present in modules.items() if not present]
        status = "OK" if not missing else "warning"
        print(f"- {status}: {block['name']} ({block['status']})")
        if missing:
            print(f"  modules absents: {', '.join(missing)}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Carte d'architecture canonique Oracle Bot.")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--json", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--check-files", action="store_true")
    parser.add_argument("--status", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    report = build_architecture_map(check_files=args.check_files or args.status)
    if args.json:
        write_json(report, args.json)
        print(f"JSON architecture ecrit: {args.json}")
    if args.html:
        write_html(report, args.html)
        print(f"HTML architecture ecrit: {args.html}")
    if args.status:
        print_status(report)
    if args.show or not any([args.json, args.html, args.status]):
        print_show(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
