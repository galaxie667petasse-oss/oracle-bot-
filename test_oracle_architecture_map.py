import json
import tempfile
from pathlib import Path

import oracle_architecture_map as arch


def main():
    report = arch.build_architecture_map(check_files=True)
    assert len(report["blocks"]) == 7
    for block in report["blocks"]:
        assert block["role"]
        assert block["modules"]
        assert block["files"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report = arch.build_architecture_map(root, check_files=True)
        assert report["blocks"][0]["module_status"]
        json_path = root / "architecture_map.json"
        html_path = root / "architecture_map.html"
        arch.write_json(report, str(json_path))
        arch.write_html(report, str(html_path))
        assert json.loads(json_path.read_text(encoding="utf-8"))["blocks"]
        assert "Architecture" in html_path.read_text(encoding="utf-8")
    print("test_oracle_architecture_map ok")


if __name__ == "__main__":
    main()
