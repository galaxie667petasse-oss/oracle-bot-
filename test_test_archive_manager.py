import tempfile
from pathlib import Path

import test_archive_manager as manager


def main():
    with tempfile.TemporaryDirectory() as tmp:
        reports = Path(tmp) / "reports"
        reports.mkdir()
        (reports / "shadow_ledger.csv").write_text("shadow_id,notes\nsh_1,demo\n", encoding="utf-8")
        (reports / "odds_snapshots.csv").write_text("snapshot_id,notes\nodds_1,test\n", encoding="utf-8")
        status = manager.status(str(reports))
        assert status["workspace_kind"] == "test"
        archive = manager.archive_current(str(reports), label="cycle_test")
        assert archive["moved"]
        assert not (reports / "shadow_ledger.csv").exists()
        reset = manager.reset_live(str(reports))
        assert Path(reset["ledger"]).exists()
        assert Path(reset["odds_snapshots"]).exists()
        archives = manager.list_archives(str(reports))
        assert archives["count"] == 1
        combined = manager.archive_and_reset(str(reports), label="again")
        assert "archive" in combined and "reset" in combined
    print("test_test_archive_manager ok")


if __name__ == "__main__":
    main()
