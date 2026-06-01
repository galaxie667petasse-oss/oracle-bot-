import json
import tempfile
from pathlib import Path

import llm_analyst_contract as llm


def main():
    template = llm.build_template()
    result = llm.validate_input(template)
    assert result["ok"]
    assert "CLV absente" in " ".join(result["warnings"])
    assert "Sample insuffisant" in " ".join(result["warnings"])
    preview = llm.render_preview(template)
    forbidden = "pari " + "conseille"
    assert forbidden not in preview.lower()
    assert "non valide" in preview
    strong = llm.build_template()
    strong["governance"]["evidence_status"] = "ready_for_deep_review"
    strong["measured_signals"]["sample_size"] = 1500
    strong["measured_signals"]["clv_percent"] = 0.01
    assert llm.validate_input(strong)["max_allowed_label"] == "analyse approfondie requise"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "llm_input.json"
        llm.write_template(str(path))
        assert llm.validate_input(json.loads(path.read_text(encoding="utf-8")))["ok"]
    print("test_llm_analyst_contract ok")


if __name__ == "__main__":
    main()
