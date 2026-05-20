from agents import agent_weights


def votes(marche_vote, valeur_vote):
    return {
        "marche": {"vote": marche_vote},
        "valeur": {"vote": valeur_vote},
        "risque": {"vote": "SURVEILLANCE"},
        "rythme": {"vote": "SURVEILLANCE"},
        "memoire": {"vote": "SURVEILLANCE"},
        "contradiction": {"vote": "SURVEILLANCE"},
    }


def row(idx, result, marche_vote, valeur_vote):
    return {
        "match_id": f"m{idx}",
        "date_key": "2026-01-01",
        "home": f"Home {idx}",
        "away": f"Away {idx}",
        "competition": "Premier League",
        "market_type": "h2h",
        "pari": f"Victoire Home {idx}",
        "odds": 2.0,
        "result": result,
        "agent_votes": votes(marche_vote, valeur_vote),
    }


def historical_row(idx, result, odds):
    return {
        "match_id": f"h{idx}",
        "date_key": "2026-01-02",
        "home": f"Hist Home {idx}",
        "away": f"Hist Away {idx}",
        "competition": "Premier League",
        "market_type": "h2h",
        "pari": f"Victoire Hist Home {idx}",
        "odds": odds,
        "result": result,
        "shadow": True,
        "visible": False,
    }


def main():
    wins = [row(i, "win", "ACCEPTE", "REFUSE") for i in range(10)]
    losses = [row(i + 10, "loss", "REFUSE", "ACCEPTE") for i in range(10)]
    historical = [historical_row(i, "win" if i % 2 == 0 else "loss", 1.55 + i * 0.2) for i in range(10)]
    db = {"scans": {"2026-01-01": {"picks": wins, "candidates": losses}, "2026-01-02": {"picks": [], "candidates": historical}}}
    weights = agent_weights(db)
    assert db["agent_weight_samples"] == 30
    assert all("agent_votes" in p for p in historical)
    assert weights["marche"] > 1.0
    assert weights["valeur"] < 1.0
    print("test_agent_weights ok")


if __name__ == "__main__":
    main()
