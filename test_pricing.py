import math

from pricing import (
    edge_probability,
    expected_value,
    fair_odds,
    implied_probability,
    market_margin,
    remove_vig_1x2,
    remove_vig_two_way,
)


def approx(left, right, tolerance=1e-9):
    return abs(left - right) <= tolerance


def main():
    assert implied_probability(2.0) == 0.5
    assert implied_probability("4,00") == 0.25

    for invalid in (None, "", "abc", 0, 1.0, float("nan"), float("inf")):
        assert implied_probability(invalid) is None

    h2h = remove_vig_1x2(2.0, 3.5, 4.0)
    assert h2h is not None
    assert approx(sum(h2h.values()), 1.0)
    assert h2h["home"] > h2h["away"]

    two_way = remove_vig_two_way(1.90, 2.00)
    assert two_way is not None
    assert approx(sum(two_way.values()), 1.0)
    assert two_way["over"] > two_way["under"]

    assert fair_odds(0.5) == 2.0
    assert fair_odds(0) is None
    assert fair_odds(None) is None

    assert approx(expected_value(0.5, 2.10), 0.05)
    assert expected_value(0.5, 1.0) is None
    assert expected_value("abc", 2.0) is None

    assert approx(edge_probability(0.55, 0.50), 0.05)
    assert approx(market_margin([0.50, 0.30, 0.25]), 0.05)
    assert market_margin([0.50, math.nan]) is None
    assert remove_vig_1x2(2.0, 0, 4.0) is None
    assert remove_vig_two_way(1.90, "abc") is None

    print("test_pricing ok")


if __name__ == "__main__":
    main()
