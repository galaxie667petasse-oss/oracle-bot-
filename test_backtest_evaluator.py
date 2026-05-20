from contextlib import redirect_stdout
from io import StringIO

from backtest_evaluator import (
    _period_conclusion,
    build_favorite_report,
    build_stability_report,
    build_train_context,
    evaluate_backtest,
    max_drawdown,
    print_favorite_report,
    print_stability_report,
    select_strategy_records,
    split_train_test,
    summarize_records,
    threshold_sweep,
)


def record(idx, date_key, market_type, odds, result, council_score=8.0, rejects=0, **extra):
    item = {
        "match_id": f"bt{idx}",
        "date_key": date_key,
        "home": f"Home {idx}",
        "away": f"Away {idx}",
        "competition": "Premier League",
        "market_type": market_type,
        "pari": f"{market_type}-{idx}",
        "odds": odds,
        "result": result,
        "shadow": True,
        "decision": "SURVEILLANCE",
        "council_score": council_score,
        "agent_rejects": rejects,
    }
    item.update(extra)
    return item


def db_from(records):
    scans = {}
    for item in records:
        scan = scans.setdefault(item["date_key"], {"picks": [], "candidates": []})
        scan["candidates"].append(item)
    return {"scans": scans}


def main():
    train = [
        record(f"tr{i}", "2022-01-01", "h2h", 3.4, "win" if i < 80 else "loss", council_score=3)
        for i in range(320)
    ]
    test = [
        record("val1", "2023-06-01", "total", 1.7, "win"),
        record("te1", "2024-01-01", "total", 1.8, "win"),
        record("te2", "2024-01-02", "total", 2.1, "loss"),
        record("te3", "2024-01-03", "h2h", 3.1, "loss"),
        record("te4", "2024-01-04", "draw", 3.4, "loss"),
    ]
    db = db_from(train + test)

    report = evaluate_backtest(db, "2023-12-31", "2024-01-01")
    assert report["train"]["samples"] == 321
    assert report["test"]["samples"] == 4
    assert "h2h" in report["train"]["by_market"]
    assert report["train"]["by_market"]["h2h"]["n"] == 320

    roi_sample = summarize_records([
        record("roi1", "2024-02-01", "total", 2.5, "win"),
        record("roi2", "2024-02-02", "total", 2.0, "loss"),
    ], include_groups=False)
    assert roi_sample["profit"] == 0.5
    assert roi_sample["roi"] == 25.0

    dd = max_drawdown([
        record("dd1", "2024-03-01", "total", 2.0, "win"),
        record("dd2", "2024-03-02", "total", 2.0, "loss"),
        record("dd3", "2024-03-03", "total", 2.0, "loss"),
    ])
    assert dd == 2.0

    baseline = report["strategies"]["baseline_all"]
    no_blocked = report["strategies"]["no_blocked_segments"]
    strict = report["strategies"]["strict_oracle"]
    relaxed = report["strategies"]["oracle_relaxed"]
    balanced = report["strategies"]["oracle_balanced"]
    oracle_strict = report["strategies"]["oracle_strict"]
    assert no_blocked["picks"] < baseline["picks"]
    assert strict["picks"] <= baseline["picks"]
    assert oracle_strict["picks"] <= balanced["picks"] <= relaxed["picks"] <= baseline["picks"]

    train_records, test_records = split_train_test(train + test, "2023-12-31", "2024-01-01")
    train_db = build_train_context(train_records)
    totals = select_strategy_records("totals_only", test_records, train_db)
    assert totals
    assert all(item["market_type"] == "total" for item in totals)

    empty_test = evaluate_backtest(db_from(train), "2023-12-31", "2024-01-01")
    for stat in empty_test["strategies"].values():
        assert stat["picks"] == 0

    modern = evaluate_backtest(db, preset="modern")
    assert modern["params"]["train_from"] == "2015-01-01"
    assert modern["train"]["samples"] == 320
    assert modern["validation"]["samples"] == 1
    assert modern["test"]["samples"] == 4

    recent = evaluate_backtest(db, preset="recent")
    assert recent["params"]["train_from"] == "2020-01-01"
    assert recent["train"]["samples"] == 321
    assert "recent_only_oracle" in recent["strategies"]

    long = evaluate_backtest(db, preset="long")
    assert long["params"]["test_from"] == "2023-01-01"
    assert long["test"]["samples"] == 5

    label = _period_conclusion({
        "modern_2015_2019": {"picks": 200, "roi": 3.6},
        "recent_2020_2023": {"picks": 200, "roi": 4.0},
        "test_2024_plus": {"picks": 200, "roi": -1.3},
    })
    assert label == "positif train/recent mais non confirme sur test final"

    sweep_train = [record(f"s-tr-{i}", "2022-01-01", "total", 1.55, "win") for i in range(120)]
    sweep_validation = [record(f"s-va-{i}", "2023-01-01", "total", 1.55, "win") for i in range(120)]
    sweep_test = [record(f"s-te-{i}", "2024-01-01", "total", 1.55, "loss") for i in range(120)]
    sweep = threshold_sweep(sweep_train, sweep_validation, sweep_test)
    assert sweep["top_train_rules"]
    assert all(entry["selection_basis"] == "train_et_validation_sans_test" for entry in sweep["top_train_rules"])
    assert sweep["rejected_train_positive_test_negative"]

    empty_strategy = summarize_records([], include_groups=True)
    assert empty_strategy["picks"] == 0
    assert empty_strategy["roi"] == 0.0

    fav_train = [
        record(f"fav-tr-{i}", "2022-01-01", "h2h", 1.70, "win", import_family="home", home_elo=1700, away_elo=1600, form3_home=6, form3_away=3, form5_home=10, form5_away=7)
        for i in range(320)
    ]
    fav_validation = [
        record(f"fav-va-{i}", "2023-01-01", "h2h", 1.70, "win", import_family="home", home_elo=1700, away_elo=1600, form3_home=6, form3_away=3, form5_home=10, form5_away=7)
        for i in range(20)
    ]
    fav_test_bad = [
        record(f"fav-te-{i}", "2024-01-01", "h2h", 1.70, "loss", import_family="home", home_elo=1700, away_elo=1600, form3_home=6, form3_away=3, form5_home=10, form5_away=7)
        for i in range(320)
    ]
    fav_test_weak = [
        record(f"fav-weak-{i}", "2024-02-01", "h2h", 1.35, "win", import_family="away", home_elo=1500, away_elo=1580, form3_home=2, form3_away=5, form5_home=4, form5_away=8)
        for i in range(2)
    ]
    favorite = build_favorite_report(db_from(fav_train + fav_validation + fav_test_bad + fav_test_weak))
    buffer = StringIO()
    with redirect_stdout(buffer):
        print_favorite_report(favorite)
    assert "Rapport favoris H2H" in buffer.getvalue()
    assert favorite["overall"]["train"]["picks"] == 320
    assert favorite["overall"]["validation"]["picks"] == 20
    assert favorite["overall"]["test"]["picks"] == 322
    odds_group = next(group for group in favorite["groups"] if group["label"] == "Tranches de cotes")
    by_label = {entry["label"]: entry for entry in odds_group["segments"]}
    assert by_label["1.60 <= cote < 1.80"]["status"] == "non confirme sur test"
    assert by_label["cote < 1.40"]["status"] == "echantillon faible"

    stable_train = [
        record(f"stab-tr-{i}", "2022-01-01", "h2h", 1.70, "win", import_family="home")
        for i in range(320)
    ]
    stable_validation = [
        record(f"stab-va-{i}", "2023-01-01", "h2h", 1.70, "win", import_family="home")
        for i in range(320)
    ]
    stable_2024 = [
        record(f"stab-24-{i}", "2024-01-01", "h2h", 1.70, "win", import_family="home")
        for i in range(320)
    ]
    stable_2025_bad = [
        record(f"stab-25-{i}", "2025-01-01", "h2h", 1.70, "loss", import_family="home")
        for i in range(320)
    ]
    weak_2024 = [
        record(f"weak-24-{i}", "2024-01-01", "draw", 3.0, "win")
        for i in range(20)
    ]
    stability = build_stability_report(db_from(stable_train + stable_validation + stable_2024 + stable_2025_bad + weak_2024))
    buffer = StringIO()
    with redirect_stdout(buffer):
        print_stability_report(stability)
    assert "Rapport de stabilite annuelle" in buffer.getvalue()
    by_key = {entry["key"]: entry for entry in stability["strategies"]}
    h2h_all = by_key["h2h_favorites_all"]
    assert h2h_all["annual"]["2024"]["roi"] > 0
    assert h2h_all["annual"]["2025"]["roi"] < 0
    assert h2h_all["score"]["positive_years"] >= 3
    assert h2h_all["score"]["negative_years"] >= 1
    assert h2h_all["stability_note"] == "degradation recente"
    assert not h2h_all["candidate_allowed"]
    draw_high = by_key["draw_high_watchlist"]
    assert draw_high["stability_note"] == "echantillon faible"

    print("test_backtest_evaluator ok")


if __name__ == "__main__":
    main()
