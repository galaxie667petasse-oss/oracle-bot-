import argparse
import importlib
import importlib.util
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence


ESSENTIAL_FILES = [
    "main.py",
    "Dockerfile",
    "README.md",
    "PROJECT_STATUS.md",
    "pricing.py",
    "feature_builder.py",
    "model_trainer.py",
    "benchmark_governance.py",
    "decision_policy.py",
    "external_xg_features.py",
    "xg_model_lab.py",
    "xg_dataset_quality.py",
    "understat_xg_pipeline.py",
    "understat_probe.py",
    "clv_analysis.py",
    "calibration_report.py",
    "statistical_validation.py",
    "backtest_evaluator.py",
    "external_xg_lab.py",
    "team_name_normalizer.py",
    "join_diagnostics.py",
    "multi_league_xg_aggregator.py",
    "clv_readiness_report.py",
    "closing_odds_probe.py",
    "features_closing_enricher.py",
    "shadow_ledger.py",
    "closing_manual_import.py",
    "shadow_clv_report.py",
    "daily_shadow_candidates.py",
    "shadow_templates.py",
    "results_manual_import.py",
    "shadow_workflow.py",
    "oracle_ops.py",
    "shadow_quality_audit.py",
    "evidence_gate.py",
    "shadow_simulator.py",
    "sample_size_planner.py",
    "shadow_message_formatter.py",
    "odds_source_config.py",
    "odds_normalizer.py",
    "odds_snapshot_store.py",
    "manual_odds_import.py",
    "api_football_odds_adapter.py",
    "the_odds_api_adapter.py",
    "odds_to_shadow.py",
    "odds_closing_matcher.py",
    "odds_source_quality_report.py",
    "odds_lab_wizard.py",
    "odds_intake_audit.py",
    "odds_e2e_demo.py",
    "oracle_architecture_map.py",
    "pipeline_contracts.py",
    "llm_analyst_contract.py",
    "restitution_schema.py",
    "progress_loop.py",
    "oracle_project_scorecard.py",
    "agent_orchestrator_dryrun.py",
    "test_archive_manager.py",
    "real_observation_guard.py",
    "matchday_pack.py",
    "matchday_runner.py",
    "config/odds_sources.example.json",
    "docs/canonical_architecture.md",
    "docs/llm_analyst_role.md",
    "docs/restitution_standard.md",
    "docs/progressive_loop.md",
    "docs/local_machine_strategy.md",
    "report_runner.py",
    "dashboard_builder.py",
    "model_registry.json",
]

SENSITIVE_PATTERNS = [
    "oracle_db.json",
    "oracle_db_backup_*.json",
    "oracle_db_archive_*.json",
    "data/",
    "external_data/",
    ".env",
    "variable/",
    "reports/",
    "reports/odds_snapshots.csv",
    "reports/manual_odds_snapshot*.csv",
    "config/odds_sources.json",
    "*.env",
]

MAIN_TESTS = [
    "test_pricing.py",
    "test_feature_builder.py",
    "test_model_trainer.py",
    "test_backtest_evaluator.py",
    "test_report_runner.py",
    "test_xgabora_dataset_import.py",
    "test_external_xg_lab.py",
    "test_team_name_normalizer.py",
    "test_join_diagnostics.py",
    "test_multi_league_xg_aggregator.py",
    "test_clv_readiness_report.py",
    "test_closing_odds_probe.py",
    "test_features_closing_enricher.py",
    "test_shadow_ledger.py",
    "test_closing_manual_import.py",
    "test_shadow_clv_report.py",
    "test_daily_shadow_candidates.py",
    "test_shadow_templates.py",
    "test_results_manual_import.py",
    "test_shadow_workflow.py",
    "test_oracle_ops.py",
    "test_shadow_quality_audit.py",
    "test_evidence_gate.py",
    "test_shadow_simulator.py",
    "test_sample_size_planner.py",
    "test_shadow_message_formatter.py",
    "test_odds_source_config.py",
    "test_odds_normalizer.py",
    "test_odds_snapshot_store.py",
    "test_manual_odds_import.py",
    "test_api_football_odds_adapter.py",
    "test_the_odds_api_adapter.py",
    "test_odds_to_shadow.py",
    "test_odds_closing_matcher.py",
    "test_odds_source_quality_report.py",
    "test_odds_lab_wizard.py",
    "test_odds_intake_audit.py",
    "test_odds_e2e_demo.py",
    "test_oracle_architecture_map.py",
    "test_pipeline_contracts.py",
    "test_llm_analyst_contract.py",
    "test_restitution_schema.py",
    "test_progress_loop.py",
    "test_oracle_project_scorecard.py",
    "test_agent_orchestrator_dryrun.py",
    "test_test_archive_manager.py",
    "test_real_observation_guard.py",
    "test_matchday_pack.py",
    "test_matchday_runner.py",
    "test_benchmark_governance.py",
    "test_decision_policy.py",
    "test_external_xg_features.py",
    "test_xg_model_lab.py",
    "test_xg_dataset_quality.py",
    "test_understat_xg_pipeline.py",
    "test_understat_probe.py",
    "test_clv_analysis.py",
    "test_calibration_report.py",
    "test_statistical_validation.py",
]

IMPORT_MODULES = [
    "pricing",
    "feature_builder",
    "model_trainer",
    "benchmark_governance",
    "decision_policy",
    "external_xg_features",
    "xg_model_lab",
    "xg_dataset_quality",
    "understat_xg_pipeline",
    "understat_probe",
    "clv_analysis",
    "calibration_report",
    "statistical_validation",
    "backtest_evaluator",
    "report_runner",
    "dashboard_builder",
    "external_dataset_probe",
    "external_join_plan",
    "external_xg_lab",
    "team_name_normalizer",
    "join_diagnostics",
    "multi_league_xg_aggregator",
    "clv_readiness_report",
    "closing_odds_probe",
    "features_closing_enricher",
    "shadow_ledger",
    "closing_manual_import",
    "shadow_clv_report",
    "daily_shadow_candidates",
    "shadow_templates",
    "results_manual_import",
    "shadow_workflow",
    "oracle_ops",
    "shadow_quality_audit",
    "evidence_gate",
    "shadow_simulator",
    "sample_size_planner",
    "shadow_message_formatter",
    "odds_source_config",
    "odds_normalizer",
    "odds_snapshot_store",
    "manual_odds_import",
    "api_football_odds_adapter",
    "the_odds_api_adapter",
    "odds_to_shadow",
    "odds_closing_matcher",
    "odds_source_quality_report",
    "odds_lab_wizard",
    "odds_intake_audit",
    "odds_e2e_demo",
    "oracle_architecture_map",
    "pipeline_contracts",
    "llm_analyst_contract",
    "restitution_schema",
    "progress_loop",
    "oracle_project_scorecard",
    "agent_orchestrator_dryrun",
    "test_archive_manager",
    "real_observation_guard",
    "matchday_pack",
    "matchday_runner",
]

OFFLINE_COMMAND_FILES = [
    "feature_builder.py",
    "model_trainer.py",
    "benchmark_governance.py",
    "decision_policy.py",
    "external_xg_features.py",
    "xg_model_lab.py",
    "xg_dataset_quality.py",
    "understat_xg_pipeline.py",
    "understat_probe.py",
    "clv_analysis.py",
    "calibration_report.py",
    "statistical_validation.py",
    "backtest_evaluator.py",
    "report_runner.py",
    "dashboard_builder.py",
    "external_dataset_probe.py",
    "external_join_plan.py",
    "external_xg_lab.py",
    "team_name_normalizer.py",
    "join_diagnostics.py",
    "multi_league_xg_aggregator.py",
    "clv_readiness_report.py",
    "closing_odds_probe.py",
    "features_closing_enricher.py",
    "shadow_ledger.py",
    "closing_manual_import.py",
    "shadow_clv_report.py",
    "daily_shadow_candidates.py",
    "shadow_templates.py",
    "results_manual_import.py",
    "shadow_workflow.py",
    "oracle_ops.py",
    "shadow_quality_audit.py",
    "evidence_gate.py",
    "shadow_simulator.py",
    "sample_size_planner.py",
    "shadow_message_formatter.py",
    "odds_source_config.py",
    "odds_normalizer.py",
    "odds_snapshot_store.py",
    "manual_odds_import.py",
    "api_football_odds_adapter.py",
    "the_odds_api_adapter.py",
    "odds_to_shadow.py",
    "odds_closing_matcher.py",
    "odds_source_quality_report.py",
    "odds_lab_wizard.py",
    "odds_intake_audit.py",
    "odds_e2e_demo.py",
    "oracle_architecture_map.py",
    "pipeline_contracts.py",
    "llm_analyst_contract.py",
    "restitution_schema.py",
    "progress_loop.py",
    "oracle_project_scorecard.py",
    "agent_orchestrator_dryrun.py",
    "test_archive_manager.py",
    "real_observation_guard.py",
    "matchday_pack.py",
    "matchday_runner.py",
]

TELEGRAM_FORBIDDEN_SNIPPETS = [
    "import bot_app",
    "import bot_app_v52",
    "from bot_app",
    "from bot_app_v52",
    "Application.builder",
    "run_polling(",
    "TELEGRAM_BOT_TOKEN",
]


@dataclass
class AuditResult:
    ok: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    def add_ok(self, message: str) -> None:
        self.ok.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_recommendation(self, message: str) -> None:
        self.recommendations.append(message)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _normalise_gitignore_line(line: str) -> str:
    cleaned = line.strip().replace("\\", "/")
    if cleaned.startswith("./"):
        cleaned = cleaned[2:]
    return cleaned


def _pattern_present(lines: Sequence[str], pattern: str) -> bool:
    wanted = _normalise_gitignore_line(pattern).rstrip("/")
    for line in lines:
        cleaned = _normalise_gitignore_line(line)
        if not cleaned or cleaned.startswith("#"):
            continue
        cleaned = cleaned.rstrip("/")
        if cleaned == wanted or wanted.startswith(cleaned + "/"):
            return True
    return False


def check_essential_files(root: Path, result: AuditResult) -> None:
    missing = [name for name in ESSENTIAL_FILES if not (root / name).exists()]
    if missing:
        result.add_error("Fichiers essentiels absents: " + ", ".join(missing))
    else:
        result.add_ok("Tous les fichiers essentiels de la release candidate sont presents.")


def check_gitignore(root: Path, result: AuditResult) -> None:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        result.add_error(".gitignore absent: les fichiers sensibles ne sont pas proteges.")
        return
    lines = _read_text(gitignore).splitlines()
    missing = [pattern for pattern in SENSITIVE_PATTERNS if not _pattern_present(lines, pattern)]
    if missing:
        result.add_error(".gitignore incomplet pour: " + ", ".join(missing))
    else:
        result.add_ok(".gitignore couvre les fichiers sensibles attendus.")


def _git_ls_files(root: Path, patterns: Iterable[str]) -> List[str]:
    command = ["git", "ls-files", "--", *patterns]
    completed = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "git ls-files a echoue")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def check_sensitive_tracking(root: Path, result: AuditResult, use_git: bool = True) -> None:
    if not use_git:
        result.add_warning("Verification git des fichiers sensibles ignoree par le test.")
        return
    try:
        tracked = _git_ls_files(root, SENSITIVE_PATTERNS)
    except Exception as exc:
        result.add_warning(f"Impossible de verifier les fichiers trackes par git: {exc}")
        return
    if tracked:
        result.add_error("Fichiers sensibles suivis par git: " + ", ".join(tracked))
    else:
        result.add_ok("Aucun fichier sensible attendu n'est suivi par git.")


def check_odds_secret_hygiene(root: Path, result: AuditResult, use_git: bool = True) -> None:
    if not use_git:
        result.add_warning("Verification git des secrets odds ignoree par le test.")
        return
    try:
        tracked_config = _git_ls_files(root, ["config/odds_sources.json", ".env", "*.env", "reports/odds_snapshots.csv", "reports/manual_odds_snapshot*.csv"])
        tracked_files = _git_ls_files(root, ["*.py", "*.md", "*.json", "*.txt", "config/*"])
    except Exception as exc:
        result.add_warning(f"Impossible de verifier les secrets odds par git: {exc}")
        return
    if tracked_config:
        result.add_error("Fichiers odds/secrets suivis par git: " + ", ".join(tracked_config))
    else:
        result.add_ok("Aucun fichier local odds_sources/.env/odds_snapshots sensible n'est suivi par git.")
    risky = []
    forbidden_assignments = ["API_FOOTBALL" + "_KEY=", "THE_ODDS_API" + "_KEY="]
    for rel in tracked_files:
        path = root / rel
        text = _read_text(path)
        if any(snippet in text for snippet in forbidden_assignments):
            risky.append(rel)
    if risky:
        result.add_error("Affectation de cle API trouvee dans fichiers suivis: " + ", ".join(risky))
    else:
        result.add_ok("Aucune affectation de cle API odds detectee dans les fichiers suivis.")
    fixture_risky = []
    for rel in _git_ls_files(root, ["tests/fixtures/*"]):
        text = _read_text(root / rel)
        if "sk_live" in text or "secret" in text.lower() or "api_key" in text.lower():
            fixture_risky.append(rel)
    if fixture_risky:
        result.add_error("Fixture potentiellement secrete: " + ", ".join(fixture_risky))
    else:
        result.add_ok("Les fixtures odds ne contiennent pas de cle evidente.")


def check_no_network_safety(root: Path, result: AuditResult) -> None:
    problems = []
    for filename in ["api_football_odds_adapter.py", "the_odds_api_adapter.py"]:
        text = _read_text(root / filename)
        if text.strip() == "# fichier test":
            continue
        if "--allow-network" not in text or "Reseau refuse par defaut" not in text:
            problems.append(filename)
    if problems:
        result.add_error("Adaptateurs reseau sans garde --allow-network clair: " + ", ".join(problems))
    else:
        result.add_ok("Les adaptateurs odds gardent le reseau bloque par defaut.")


def check_forbidden_wording(root: Path, result: AuditResult) -> None:
    problems = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        if rel.startswith("reports/") or rel.startswith("external_data/") or rel.startswith("__pycache__/") or ".git/" in rel:
            continue
        text = _read_text(path).lower()
        forbidden_terms = ["pari " + "conseillé", "pari " + "conseille"]
        if any(term in text for term in forbidden_terms):
            problems.append(rel)
    if problems:
        result.add_error("Expression interdite detectee: " + ", ".join(problems))
    else:
        result.add_ok("Expression interdite absente hors reports/external_data.")


def check_tests(root: Path, result: AuditResult) -> None:
    missing = [name for name in MAIN_TESTS if not (root / name).exists()]
    if missing:
        result.add_warning("Tests principaux absents: " + ", ".join(missing))
    else:
        result.add_ok("Les tests principaux sont presents.")


def check_imports(result: AuditResult) -> None:
    failed = []
    for module_name in IMPORT_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:
            failed.append(f"{module_name} ({exc})")
    if failed:
        result.add_error("Modules principaux non importables: " + "; ".join(failed))
    else:
        result.add_ok("Les modules principaux s'importent sans lancer le bot.")


def check_telegram_guard(root: Path, result: AuditResult) -> None:
    problems = []
    for filename in OFFLINE_COMMAND_FILES:
        path = root / filename
        if not path.exists():
            continue
        text = _read_text(path)
        for snippet in TELEGRAM_FORBIDDEN_SNIPPETS:
            if snippet in text:
                problems.append(f"{filename}: {snippet}")
    if problems:
        result.add_error("Commande locale susceptible de lancer Telegram: " + "; ".join(problems))
    else:
        result.add_ok("Les commandes locales auditees ne lancent pas Telegram.")

    try:
        report_runner = importlib.import_module("report_runner")
        commands = report_runner.command_set("full")
        risky = [
            " ".join(command.args)
            for command in commands
            if any(token in " ".join(command.args) for token in ("main.py", "bot_app.py", "bot_app_v52.py"))
        ]
        if risky:
            result.add_error("report_runner contient une commande Telegram: " + "; ".join(risky))
        else:
            result.add_ok("report_runner reste limite aux rapports locaux.")
    except Exception as exc:
        result.add_warning(f"Impossible d'inspecter report_runner: {exc}")


def check_dependencies(root: Path, result: AuditResult) -> None:
    requirements = _read_text(root / "requirements.txt").lower()
    docs = (_read_text(root / "README.md") + "\n" + _read_text(root / "COMMANDS.md")).lower()

    if importlib.util.find_spec("numpy") is None:
        result.add_warning("numpy absent: model_trainer.py affichera une erreur claire et les autres tests doivent rester utilisables.")
    elif "numpy" not in requirements and "numpy" not in docs:
        result.add_warning("numpy est utilise par le ML local mais n'est pas documente dans README.md ou COMMANDS.md.")
    else:
        result.add_ok("Dependance numpy documentee ou deja disponible pour le ML local.")

    if importlib.util.find_spec("sklearn") is None:
        result.add_ok("sklearn absent: il reste optionnel et model_trainer.py doit l'ignorer proprement.")
    else:
        result.add_ok("sklearn disponible: les modeles legers optionnels peuvent etre entraines localement.")

    if importlib.util.find_spec("soccerdata") is None:
        result.add_ok("soccerdata absent: optionnel pour understat_probe.py; installer avec python -m pip install soccerdata si besoin.")
    else:
        result.add_ok("soccerdata disponible: le probe Understat peut etre lance explicitement.")


def check_docs(root: Path, result: AuditResult) -> None:
    readme = _read_text(root / "README.md").lower()
    status = _read_text(root / "PROJECT_STATUS.md").lower()
    required_readme_sections = [
        "vision du projet",
        "ce que le bot fait",
        "ce que le bot ne fait pas",
        "architecture",
        "pipeline local",
        "etat actuel",
        "roadmap",
    ]
    missing_readme = [section for section in required_readme_sections if section not in readme]
    if missing_readme:
        result.add_warning("README.md incomplet pour: " + ", ".join(missing_readme))
    else:
        result.add_ok("README.md contient les sections principales de stabilisation.")

    if ("v7.0" not in status and "v7.2" not in status) or ("aucune strategie robuste" not in status and "aucun signal robuste" not in status):
        result.add_warning("PROJECT_STATUS.md doit mentionner V7/V8 et l'absence de strategie robuste activee.")
    else:
        result.add_ok("PROJECT_STATUS.md resume l'etat prudent V7/V8.")


def run_audit(root: Path, check_import_modules: bool = True, use_git: bool = True) -> AuditResult:
    result = AuditResult()
    root = root.resolve()
    check_essential_files(root, result)
    check_gitignore(root, result)
    check_sensitive_tracking(root, result, use_git=use_git)
    check_odds_secret_hygiene(root, result, use_git=use_git)
    check_no_network_safety(root, result)
    check_forbidden_wording(root, result)
    check_tests(root, result)
    if check_import_modules:
        check_imports(result)
    check_telegram_guard(root, result)
    check_dependencies(root, result)
    check_docs(root, result)
    result.add_recommendation("Conserver le bot en mode analyse prudente tant qu'aucun signal robuste n'est valide en test 2024+.")
    result.add_recommendation("Executer le quality gate Understat xG multi-saisons avant toute conclusion modele.")
    result.add_recommendation("Ne jamais utiliser les features post-match pour predire le meme match en conditions live.")
    return result


def _print_group(title: str, items: Sequence[str], empty: str) -> None:
    print(title)
    if not items:
        print(f"- {empty}")
        return
    for item in items:
        print(f"- {item}")


def print_audit(result: AuditResult) -> None:
    print("Audit projet Oracle Football Bot")
    print("")
    _print_group("OK", result.ok, "Aucun point OK enregistre.")
    print("")
    _print_group("Warnings", result.warnings, "Aucun warning.")
    print("")
    _print_group("Erreurs bloquantes", result.errors, "Aucune erreur bloquante.")
    print("")
    _print_group("Recommandations", result.recommendations, "Aucune recommandation.")
    print("")
    if result.success:
        print("Statut release candidate: OK local prudent.")
    else:
        print("Statut release candidate: bloque, corriger les erreurs ci-dessus.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Audit local Oracle Bot sans modifier la memoire.")
    parser.add_argument("--root", default=".", help="Racine du projet a auditer")
    parser.add_argument("--no-imports", action="store_true", help="Ignore l'import des modules principaux")
    parser.add_argument("--no-git", action="store_true", help="Ignore la verification git des fichiers sensibles")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    result = run_audit(Path(args.root), check_import_modules=not args.no_imports, use_git=not args.no_git)
    print_audit(result)
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
