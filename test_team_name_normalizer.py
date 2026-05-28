import tempfile
from pathlib import Path

from team_name_normalizer import (
    apply_aliases,
    export_team_mapping_suggestions,
    normalize_team_name,
    suggest_team_aliases,
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
    assert normalize_team_name("Atlético Madrid", league="La-Liga") == "atletico madrid"
    assert normalize_team_name("Atletico Madrid", league="La-Liga") == "atletico madrid"
    assert normalize_team_name("Athletic Club", league="La-Liga") == "athletic bilbao"
    assert normalize_team_name("Athletic Bilbao", league="La-Liga") == "athletic bilbao"
    assert normalize_team_name("Ath Bilbao", league="La-Liga") == "athletic bilbao"
    assert normalize_team_name("Ath Madrid", league="La-Liga") == "atletico madrid"
    assert normalize_team_name("Betis", league="La-Liga") == "real betis"
    assert normalize_team_name("Cádiz", league="La-Liga") == "cadiz"
    assert normalize_team_name("Leganés", league="La-Liga") == "leganes"
    assert normalize_team_name("Girona FC", league="La-Liga") == "girona"
    assert normalize_team_name("CA Osasuna", league="La-Liga") == "osasuna"
    assert normalize_team_name("SD Huesca", league="La-Liga") == "huesca"
    assert normalize_team_name("Athletic Club", league="La-Liga", use_aliases=False) == "athletic"
    assert apply_aliases("Sociedad", league="La-Liga") == "real sociedad"

    assert team_name_similarity("Man United", "Manchester United") == 1.0
    assert team_name_similarity("West Ham Utd", "West Ham United") >= 0.8
    assert team_name_similarity("Atlético Madrid", "Atletico Madrid") == 1.0
    assert team_name_similarity("Athletic Club", "Athletic Bilbao") == 1.0

    suggestions = suggest_team_matches(
        ["Man United", "Spurs", "Nott'm Forest"],
        ["Manchester United", "Tottenham", "Nottingham Forest", "Chelsea"],
    )
    mapping = {item["external_name"]: item["suggested_xgabora_name"] for item in suggestions}
    assert mapping["Man United"] == "Manchester United"
    assert mapping["Spurs"] == "Tottenham"
    assert mapping["Nott'm Forest"] == "Nottingham Forest"
    liga_suggestions = suggest_team_aliases(
        ["Athletic Club", "Betis", "Rayo Vallecano"],
        ["Athletic Bilbao", "Real Betis", "Vallecano"],
        league="La-Liga",
    )
    assert {item["normalized_external"] for item in liga_suggestions} >= {"athletic bilbao", "real betis", "rayo vallecano"}

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "reports" / "team_mapping_suggestions.csv"
        written = export_team_mapping_suggestions(suggestions, str(output))
        assert written.exists()
        assert "Man United" in written.read_text(encoding="utf-8")

    print("test_team_name_normalizer ok")


if __name__ == "__main__":
    main()
