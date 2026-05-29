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

    assert normalize_team_name("Bayer Leverkusen", league="Bundesliga") == "leverkusen"
    assert normalize_team_name("Eintracht Frankfurt", league="Bundesliga") == "ein frankfurt"
    assert normalize_team_name("FC Heidenheim", league="Bundesliga") == "heidenheim"
    assert normalize_team_name("Borussia Dortmund", league="Bundesliga") == "dortmund"
    assert normalize_team_name("Mönchengladbach", league="Bundesliga") == "mgladbach"
    assert normalize_team_name("Borussia Monchengladbach", league="Bundesliga") == "mgladbach"
    assert normalize_team_name("Borussia M.Gladbach", league="Bundesliga") == "mgladbach"
    assert normalize_team_name("Gladbach", league="Bundesliga") == "mgladbach"
    assert normalize_team_name("RB Leipzig", league="Bundesliga") == "rb leipzig"
    assert normalize_team_name("RasenBallsport Leipzig", league="Bundesliga") == "rb leipzig"
    assert normalize_team_name("FC Bayern München", league="Bundesliga") == "bayern munich"
    assert normalize_team_name("Bayern Munchen", league="Bundesliga") == "bayern munich"
    assert normalize_team_name("SC Freiburg", league="Bundesliga") == "freiburg"
    assert normalize_team_name("TSG Hoffenheim", league="Bundesliga") == "hoffenheim"
    assert normalize_team_name("VfL Wolfsburg", league="Bundesliga") == "wolfsburg"
    assert normalize_team_name("Bremen", league="Bundesliga") == "werder bremen"
    assert normalize_team_name("1. FC Union Berlin", league="Bundesliga") == "union berlin"
    assert normalize_team_name("Hertha BSC", league="Bundesliga") == "hertha"
    assert normalize_team_name("FC Schalke 04", league="Bundesliga") == "schalke 04"
    assert normalize_team_name("Köln", league="Bundesliga") == "koln"
    assert normalize_team_name("FC Köln", league="Bundesliga") == "koln"
    assert normalize_team_name("FC Cologne", league="Bundesliga") == "koln"
    assert normalize_team_name("Mainz 05", league="Bundesliga") == "mainz"
    assert normalize_team_name("VfB Stuttgart", league="Bundesliga") == "stuttgart"
    assert normalize_team_name("VfL Bochum", league="Bundesliga") == "bochum"
    assert normalize_team_name("SV Darmstadt 98", league="Bundesliga") == "darmstadt"
    assert normalize_team_name("Arminia Bielefeld", league="Bundesliga") == "bielefeld"
    assert normalize_team_name("Greuther Fürth", league="Bundesliga") == "greuther furth"
    assert normalize_team_name("Greuther Fuerth", league="Bundesliga") == "greuther furth"
    assert normalize_team_name("Furth", league="Bundesliga") == "greuther furth"
    assert normalize_team_name("St. Pauli", league="Bundesliga") == "st pauli"
    assert normalize_team_name("FC St. Pauli", league="Bundesliga") == "st pauli"
    assert normalize_team_name("Holstein Kiel", league="Bundesliga") == "holstein kiel"
    assert normalize_team_name("Kiel", league="Bundesliga") == "holstein kiel"

    assert normalize_team_name("Internazionale", league="Serie A") == "inter"
    assert normalize_team_name("Inter Milan", league="Serie A") == "inter"
    assert normalize_team_name("AC Milan", league="Serie A") == "milan"
    assert normalize_team_name("Juve", league="Serie A") == "juventus"
    assert normalize_team_name("AS Roma", league="Serie A") == "roma"
    assert normalize_team_name("SSC Napoli", league="Serie A") == "napoli"
    assert normalize_team_name("Hellas Verona", league="Serie A") == "verona"
    assert normalize_team_name("Parma Calcio 1913", league="Serie A") == "parma"
    assert normalize_team_name("Spezia Calcio", league="Serie A") == "spezia"
    assert normalize_team_name("US Salernitana", league="Serie A") == "salernitana"
    assert normalize_team_name("AC Monza", league="Serie A") == "monza"
    assert normalize_team_name("Bologna FC 1909", league="Serie A") == "bologna"
    assert normalize_team_name("Udinese Calcio", league="Serie A") == "udinese"
    assert normalize_team_name("Como", league="I1") == "como"
    assert normalize_team_name("Como 1907", league="I1") == "como"

    assert normalize_team_name("Paris Saint-Germain", league="Ligue 1") == "paris sg"
    assert normalize_team_name("PSG", league="Ligue 1") == "paris sg"
    assert normalize_team_name("Olympique Marseille", league="Ligue 1") == "marseille"
    assert normalize_team_name("Olympique Lyonnais", league="Ligue 1") == "lyon"
    assert normalize_team_name("AS Monaco", league="Ligue 1") == "monaco"
    assert normalize_team_name("LOSC Lille", league="Ligue 1") == "lille"
    assert normalize_team_name("RC Lens", league="Ligue 1") == "lens"
    assert normalize_team_name("Saint-Étienne", league="Ligue 1") == "st etienne"
    assert normalize_team_name("AS Saint-Etienne", league="Ligue 1") == "st etienne"
    assert normalize_team_name("Clermont Foot", league="Ligue 1") == "clermont"
    assert normalize_team_name("Le Havre AC", league="Ligue 1") == "le havre"
    assert normalize_team_name("AJ Auxerre", league="Ligue 1") == "auxerre"
    assert normalize_team_name("ESTAC Troyes", league="Ligue 1") == "troyes"
    assert normalize_team_name("Angers SCO", league="Ligue 1") == "angers"
    assert normalize_team_name("Girondins Bordeaux", league="Ligue 1") == "bordeaux"
    assert normalize_team_name("FC Sochaux-Montbeliard", league="Ligue 1") == "sochaux"
    assert normalize_team_name("EA Guingamp", league="Ligue 1") == "guingamp"
    assert normalize_team_name("Stade Malherbe Caen", league="Ligue 1") == "caen"
    assert normalize_team_name("Nîmes", league="F1") == "nimes"

    assert normalize_team_name("Athletic Club", league="La-Liga", use_aliases=False) == "athletic"
    assert apply_aliases("Sociedad", league="La-Liga") == "real sociedad"

    assert team_name_similarity("Man United", "Manchester United") == 1.0
    assert team_name_similarity("West Ham Utd", "West Ham United") >= 0.8
    assert team_name_similarity("Atlético Madrid", "Atletico Madrid") == 1.0
    assert team_name_similarity("Athletic Club", "Athletic Bilbao") == 1.0
    assert team_name_similarity("Bayer Leverkusen", "Leverkusen", league="Bundesliga") == 1.0
    assert team_name_similarity("Borussia Monchengladbach", "MGladbach", league="Bundesliga") == 1.0
    assert team_name_similarity("Internazionale", "Inter", league="Serie A") == 1.0
    assert team_name_similarity("Paris Saint Germain", "Paris SG", league="Ligue 1") == 1.0

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
