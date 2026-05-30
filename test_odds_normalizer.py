from odds_normalizer import build_snapshot_id, normalize_decimal_odds, normalize_market_type, normalize_odds_rows, normalize_side


def main():
    assert normalize_decimal_odds("2,10") == 2.1
    try:
        normalize_decimal_odds("0.5")
        raise AssertionError("probabilite acceptee")
    except ValueError:
        pass
    try:
        normalize_decimal_odds("abc")
        raise AssertionError("texte accepte")
    except ValueError:
        pass
    assert normalize_market_type("Match Winner") == "h2h"
    assert normalize_side("Home", "h2h") == "home"
    assert normalize_side("Away", "h2h") == "away"
    assert normalize_side("Draw", "h2h") == "draw"
    assert normalize_market_type("Goals Over/Under") == "total"
    assert normalize_side("Over 2.5", "total") == "over"
    row = {
        "captured_at": "2026-06-01T10:00:00",
        "source": "manual_csv",
        "league": "EPL",
        "match_date": "2026-06-01",
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "bookmaker": "Book",
        "market_type": "h2h",
        "side": "home",
        "odds": "2.10",
    }
    rows = normalize_odds_rows([row])
    assert rows[0]["validation_status"] == "valid"
    assert build_snapshot_id(rows[0]) == build_snapshot_id(rows[0])

    print("test_odds_normalizer ok")


if __name__ == "__main__":
    main()
