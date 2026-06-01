import json
import tempfile
from pathlib import Path

import restitution_schema as schema


def main():
    template = schema.build_template()
    assert schema.validate_schema(template)["ok"]
    text = schema.render_text(template)
    assert "Restitution Oracle" in text
    assert ("pari " + "conseille") not in text.lower()
    bad = schema.build_template()
    bad["decision"]["allowed_actions"].append("action agressive")
    assert not schema.validate_schema(bad)["ok"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "template.json"
        html_path = root / "preview.html"
        schema.write_template(str(path))
        data = json.loads(path.read_text(encoding="utf-8"))
        assert schema.validate_schema(data)["ok"]
        schema.write_html(data, str(html_path))
        assert html_path.exists()
    print("test_restitution_schema ok")


if __name__ == "__main__":
    main()
