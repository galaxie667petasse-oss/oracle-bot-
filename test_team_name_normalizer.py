import tempfile
from pathlib import Path

from team_name_normalizer import (
    export_team_mapping_suggestions,
    normalize_team_name,
    suggest_team_matches,
    team_name_similarity,
)


def main():
    assert normalize_team_name("Man United") == "manchester united"
    assert normalize_team_name("Manchester United FC") == "manchester united"
    assert normalize_team_name("Spurs") == "tottenham"
    assert normalize_team_name("Wolves") == "wolverhampton"
    assert normalize_team_name("Newcastle Utd") == "newcastle"
    assert normalize_team_name("Nott'm Forest") == "nottingham forest"

    assert team_name_similarity("Man United", "Manchester United") == 1.0
    assert team_name_similarity("West Ham Utd", "West Ham United") >= 0.8

    suggestions = suggest_team_matches(
        ["Man United", "Spurs", "Nott'm Forest"],
        ["Manchester United", "Tottenham", "Nottingham Forest", "Chelsea"],
    )
    mapping = {item["external_name"]: item["suggested_xgabora_name"] for item in suggestions}
    assert mapping["Man United"] == "Manchester United"
    assert mapping["Spurs"] == "Tottenham"
    assert mapping["Nott'm Forest"] == "Nottingham Forest"

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "reports" / "team_mapping_suggestions.csv"
        written = export_team_mapping_suggestions(suggestions, str(output))
        assert written.exists()
        assert "Man United" in written.read_text(encoding="utf-8")

    print("test_team_name_normalizer ok")


if __name__ == "__main__":
    main()
