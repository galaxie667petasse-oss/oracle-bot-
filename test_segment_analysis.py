from calibration import segment_adjustment_for_pick
from segment_analysis import build_segment_report


def pick(idx, market_type, odds, result, competition="Premier League", family="", elo_diff="", date_key="2021-02-01"):
    return {
        "match_id": f"m{idx}",
        "date_key": date_key,
        "home": f"Home {idx}",
        "away": f"Away {idx}",
        "competition": competition,
        "market_type": market_type,
        "pari": f"{market_type}-{idx}",
        "odds": odds,
        "result": result,
        "shadow": True,
        "import_family": family,
        "elo_diff": elo_diff,
    }


def main():
    candidates = []
    for i in range(320):
        candidates.append(pick(f"h{i:03d}", "h2h", 1.55, "win" if i < 230 else "loss", family="home", elo_diff=90))
    for i in range(320):
        candidates.append(pick(f"d{i:03d}", "draw", 3.60, "win" if i < 60 else "loss"))
    for i in range(90):
        candidates.append(pick(f"b{i:03d}", "btts", 2.00, "win" if i < 60 else "loss"))

    db = {"scans": {"2024-02-01": {"picks": [], "candidates": candidates}}}
    report = build_segment_report(db)
    db["segment_report"] = report

    assert report["samples"] == 730
    positive = report["segments"]["market_odds:h2h|low"]
    assert positive["n"] == 320
    assert positive["wins"] == 230
    assert positive["winrate"] == 71.9
    assert positive["roi"] == 11.4
    assert positive["positive_reliable"] is True

    negative = report["segments"]["market_odds:draw|very_high"]
    assert negative["n"] == 320
    assert negative["negative_strong"] is True
    assert negative["block_top"] is True

    h2h_signal = segment_adjustment_for_pick(pick("new01", "h2h", 1.55, "win", family="home", elo_diff=90), db)
    assert h2h_signal["positive_reliable"] is True
    assert h2h_signal["adjustment"] > 0

    draw_signal = segment_adjustment_for_pick(pick("new02", "draw", 3.60, "loss"), db)
    assert draw_signal["block_top"] is True
    assert draw_signal["adjustment"] < 0

    small_signal = segment_adjustment_for_pick(pick("new03", "btts", 2.00, "win"), db)
    assert small_signal["positive_reliable"] is False
    assert small_signal["adjustment"] <= 0

    archive_recent = []
    for i in range(320):
        archive_recent.append(pick(f"a{i:03d}", "total", 1.55, "win" if i < 260 else "loss", date_key="2008-01-01"))
    for i in range(320):
        archive_recent.append(pick(f"r{i:03d}", "total", 1.55, "win" if i < 120 else "loss", date_key="2021-01-01"))
    db2 = {"scans": {"mixed": {"picks": [], "candidates": archive_recent}}}
    report2 = build_segment_report(db2)
    assert "period:archive_pre2012" in report2["segments"]
    assert "period:recent_2020_2023" in report2["segments"]
    total_low = report2["segments"]["market_odds:total|low"]
    recent_total_low = report2["segments"]["market_odds_period:total|low|recent_2020_2023"]
    assert total_low["positive_reliable"] is False
    assert "ancien" in total_low["recency_note"] or "contredit" in total_low["recency_note"]
    assert recent_total_low["n"] == 320
    assert recent_total_low["period_stats"]["recent_2020_2023"]["n"] == 320

    print("test_segment_analysis ok")


if __name__ == "__main__":
    main()
