import json
import tempfile
from pathlib import Path

import external_evidence_catalog


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report = external_evidence_catalog.build_catalog()
        assert report["summary"]["sources_count"] >= 5
        assert report["summary"]["offline_sources"] >= 2
        out = root / "reports" / "external_evidence_catalog.json"
        html = root / "reports" / "external_evidence_catalog.html"
        external_evidence_catalog.write_json(report, str(out))
        external_evidence_catalog.write_html(report, str(html))
        assert json.loads(out.read_text(encoding="utf-8"))["lab_only"] is True
        assert html.exists()
        try:
            external_evidence_catalog.write_json(report, str(root / "data" / "bad.json"))
            raise AssertionError("ecriture data acceptee")
        except ValueError:
            pass
    print("test_external_evidence_catalog ok")


if __name__ == "__main__":
    main()
