from backtest_evaluator import (
    _period_conclusion,
    build_train_context,
    evaluate_backtest,
    max_drawdown,
    select_strategy_records,
    split_train_test,
    summarize_records,
    threshold_sweep,
)


def record(idx, date_key, market_type, odds, result, council_score=8.0, rejects=0):
    return {
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

    print("test_backtest_evaluator ok")


if __name__ == "__main__":
    main()
