import sys
import types
from datetime import timezone

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))

from agents import agent_weights
from store import build_learning


VOTES = {
    "marche": {"vote": "ACCEPTE"},
    "valeur": {"vote": "ACCEPTE"},
    "risque": {"vote": "SURVEILLANCE"},
    "rythme": {"vote": "SURVEILLANCE"},
    "memoire": {"vote": "SURVEILLANCE"},
    "contradiction": {"vote": "REFUSE"},
}


def pick(match_id, result, shadow=False):
    return {
        "match_id": match_id,
        "date_key": "2026-01-01",
        "home": f"Home {match_id}",
        "away": f"Away {match_id}",
        "competition": "Ligue 1",
        "market_type": "total",
        "pari": "Plus de 2.5 buts",
        "odds": 1.9,
        "result": result,
        "decision": "REFUSE" if shadow else "ACCEPTE",
        "shadow": shadow,
        "visible": not shadow,
        "agent_votes": VOTES,
    }


def main():
    db = {
        "scans": {
            "2026-01-01": {
                "picks": [pick("visible-1", "win")],
                "candidates": [pick("shadow-1", "loss", True), pick("shadow-2", "win", True)],
            }
        }
    }
    db["learning"] = build_learning(db)
    agent_weights(db)
    assert db["learning"]["samples"] == 3
    assert db["learning"]["visible_samples"] == 1
    assert db["learning"]["shadow_samples"] == 2
    assert db["agent_weight_samples"] == 3
    print("test_shadow_learning ok")


if __name__ == "__main__":
    main()
