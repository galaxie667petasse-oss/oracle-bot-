import hashlib
import tempfile
from pathlib import Path

import project_audit


def write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def digest_tree(root: Path):
    digests = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digests[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def make_minimal_project(root: Path) -> None:
    for filename in project_audit.ESSENTIAL_FILES:
        if filename.endswith(".md"):
            write(root / filename, "# Test\n\nVision du projet\nCe que le bot fait\nCe que le bot ne fait pas\nArchitecture\nPipeline local\nEtat actuel\nRoadmap\nV7.0\nV7.2\nAucune strategie robuste activee\nnumpy\n")
        else:
            write(root / filename, "# fichier test\n")
    for filename in project_audit.MAIN_TESTS:
        write(root / filename, "# test\n")
    write(root / "COMMANDS.md", "# Commandes\n\nnumpy\n")
    write(root / ".gitignore", "\n".join(project_audit.SENSITIVE_PATTERNS) + "\n")


def test_audit_read_only_and_oracle_db_optional():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        make_minimal_project(root)
        assert not (root / "oracle_db.json").exists()
        before = digest_tree(root)
        result = project_audit.run_audit(root, check_import_modules=False, use_git=False)
        after = digest_tree(root)
        assert before == after
        assert result.success


def test_sensitive_files_not_tracked_in_current_repo():
    root = Path.cwd()
    tracked = project_audit._git_ls_files(root, project_audit.SENSITIVE_PATTERNS)
    assert tracked == []


def test_release_candidate_docs_exist_and_have_sections():
    root = Path.cwd()
    assert (root / "COMMANDS.md").exists()
    assert (root / "PROJECT_STATUS.md").exists()
    assert (root / "README.md").exists()

    readme = (root / "README.md").read_text(encoding="utf-8").lower()
    for section in [
        "vision du projet",
        "ce que le bot fait",
        "ce que le bot ne fait pas",
        "architecture",
        "pipeline local",
        "memoire",
        "import historique",
        "pricing",
        "backtest",
        "ml",
        "rapports",
        "external dataset lab",
        "external xg integration lab",
        "external xg rolling",
        "understat",
        "understat xg full pipeline quality gate",
        "multi-league join diagnostics",
        "bundesliga team alias expansion",
        "big five xg completion",
        "clv readiness",
        "closing odds recovery",
        "partial clv pipeline",
        "closing column forensics",
        "shadow mode",
        "shadow ux",
        "operations center",
        "evidence gate",
        "odds source lab",
        "odds snapshot",
        "manual odds workflow",
        "odds intake",
        "canonical architecture blueprint",
        "llm analyste",
        "boucle de progression",
        "real matchday workflow",
        "human intake",
        "june collection",
        "statistical proof foundation",
        "clv",
        "reliability curves",
        "multiple testing",
        "scientific benchmark",
        "model governance",
        "model registry",
        "promotion policy",
        "decision policy",
        "telegram",
        "railway plus tard",
        "securite",
        "commandes principales",
        "etat actuel",
        "roadmap",
    ]:
        assert section in readme

    status = (root / "PROJECT_STATUS.md").read_text(encoding="utf-8").lower()
    assert "v7.0 statistical proof foundation" in status
    assert "v7.2 understat xg full pipeline quality gate" in status
    assert "v8.1 shadow ux" in status
    assert "v8.2" in status
    assert "v8.3" in status
    assert "v8.4" in status
    assert "v8.5" in status
    assert "v8.6" in status
    assert "aucun signal robuste active" in status
    assert (root / "docs" / "closing_odds_forensics.md").exists()
    assert (root / "docs" / "shadow_mode_workflow.md").exists()
    assert (root / "docs" / "operations_center.md").exists()
    assert (root / "docs" / "evidence_gate_policy.md").exists()
    assert (root / "docs" / "june_shadow_runbook.md").exists()
    assert (root / "docs" / "odds_source_lab.md").exists()
    assert (root / "docs" / "free_odds_sources.md").exists()
    assert (root / "docs" / "odds_snapshot_format.md").exists()
    assert (root / "docs" / "manual_odds_workflow.md").exists()
    assert (root / "docs" / "odds_intake_audit.md").exists()
    assert (root / "docs" / "odds_e2e_demo.md").exists()
    assert (root / "docs" / "canonical_architecture.md").exists()
    assert (root / "docs" / "llm_analyst_role.md").exists()
    assert (root / "docs" / "restitution_standard.md").exists()
    assert (root / "docs" / "progressive_loop.md").exists()
    assert (root / "docs" / "local_machine_strategy.md").exists()
    assert (root / "docs" / "real_matchday_workflow.md").exists()
    assert (root / "docs" / "test_archive_policy.md").exists()
    assert (root / "docs" / "human_intake_guardrails.md").exists()


def main():
    test_audit_read_only_and_oracle_db_optional()
    test_sensitive_files_not_tracked_in_current_repo()
    test_release_candidate_docs_exist_and_have_sections()
    print("test_project_audit ok")


if __name__ == "__main__":
    main()
