import tempfile
from pathlib import Path

import progress_loop


def main():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "reports" / "progress_loop.csv"
        progress_loop.init_progress(str(path))
        assert path.exists()
        row = progress_loop.add_entry(str(path), phase="collecter", title="Ajout cote test", status="done", notes="snapshot manuel")
        assert row["entry_id"]
        progress_loop.add_entry(str(path), phase="corriger", title="Corriger doublon", status="todo")
        summary = progress_loop.summarize_progress(str(path))
        assert summary["entries"] == 2
        assert summary["by_phase"]["collecter"] == 1
        assert summary["by_status"]["todo"] == 1
        html_path = Path(tmp) / "reports" / "progress_loop.html"
        progress_loop.write_html(str(path), str(html_path))
        assert html_path.exists()
        try:
            progress_loop.add_entry(str(path), phase="bad", title="x")
            raise AssertionError("phase invalide non bloquee")
        except ValueError:
            pass
    print("test_progress_loop ok")


if __name__ == "__main__":
    main()
