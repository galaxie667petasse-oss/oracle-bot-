import sys
import types
from datetime import timezone

sys.modules.setdefault("pytz", types.SimpleNamespace(timezone=lambda _name: timezone.utc))
sys.modules.setdefault("aiohttp", types.SimpleNamespace(ClientSession=object))

from settlement import eval_pick


def main():
    assert eval_pick({"market_type": "h2h", "home": "Alpha FC", "away": "Beta FC", "pari": "Victoire Alpha FC"}, 2, 1) == "win"
    assert eval_pick({"market_type": "h2h", "home": "Alpha FC", "away": "Beta FC", "pari": "Victoire Beta FC"}, 2, 1) == "loss"
    assert eval_pick({"market_type": "draw", "pari": "Match nul"}, 1, 1) == "win"
    assert eval_pick({"market_type": "total", "pari": "Plus de 2.5 buts"}, 2, 1) == "win"
    assert eval_pick({"market_type": "total", "pari": "Moins de 2.5 buts"}, 2, 1) == "loss"
    assert eval_pick({"market_type": "btts", "pari": "Les deux équipes marquent - Oui"}, 1, 1) == "win"
    assert eval_pick({"market_type": "btts", "pari": "Les deux équipes marquent - Non"}, 1, 0) == "win"
    print("test_settlement ok")


if __name__ == "__main__":
    main()
