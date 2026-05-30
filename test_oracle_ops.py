import tempfile
from pathlib import Path

import oracle_ops
import shadow_ledger


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitignore").write_text("reports/\nexternal_data/\n", encoding="utf-8")
        (root / "data").mkdir()
        features = root / "data" / "features_modern.csv"
        matches = root / "data" / "MATCHES.csv"
        features.write_text("date,home,away\n", encoding="utf-8")
        matches.write_text("date,home,away\n", encoding="utf-8")
        for module in oracle_ops.KEY_MODULES:
            (root / module).write_text("# module test\n", encoding="utf-8")
        ledger = root / "reports" / "shadow_ledger.csv"
        shadow_ledger.add_shadow_entry(str(ledger), match_date="2026-06-01", league="EPL", home="A", away="B", market="h2h", side="home", taken_odds="2.10")
        before_features = features.read_text(encoding="utf-8")
        before_matches = matches.read_text(encoding="utf-8")

        health = oracle_ops.build_health(root, str(ledger.relative_to(root)))
        assert health["status"] == "OK"
        daily = oracle_ops.daily_checklist("2026-06-01")
        assert len(daily["checklist"]) >= 6

        templates = oracle_ops.shadow_templates(str(ledger), str(root / "reports"))
        assert Path(templates["candidates"]).exists()
        full = oracle_ops.full_local(str(ledger), str(root / "reports"), skip_benchmark=True, skip_dashboard=True)
        assert full["shadow_summary"]["signals_total"] == 1
        assert full["quality"]["verdict"] in {"usable_with_warnings", "clean"}
        assert full["evidence"]["global_status"] in {"insufficient_evidence", "blocked", "promising_but_unvalidated"}
        assert full["optional"] == []
        odds_store = root / "reports" / "odds_snapshots.csv"
        odds_lab = oracle_ops.odds_lab(str(root / "reports"), str(odds_store))
        assert odds_lab["summary"]["rows_total"] == 0
        assert Path(odds_lab["template"]["manual_odds_template"]).exists()
        assert oracle_ops.odds_summary(str(odds_store))["rows_total"] == 0
        assert oracle_ops.odds_config_report()["config_ok"] is True
        status = oracle_ops.odds_wizard_status(str(odds_store), str(ledger), str(root / "reports"))
        assert status["snapshots_total"] == 0
        intake = oracle_ops.odds_intake_audit_report(str(root / "reports"), str(odds_store), str(ledger))
        assert intake["verdict"] in {"shadow_started", "no_data", "snapshots_only"}

        absent = oracle_ops.build_health(root / "absent", str(ledger))
        assert absent["status"] == "bloquant"
        assert features.read_text(encoding="utf-8") == before_features
        assert matches.read_text(encoding="utf-8") == before_matches

    print("test_oracle_ops ok")


if __name__ == "__main__":
    main()
