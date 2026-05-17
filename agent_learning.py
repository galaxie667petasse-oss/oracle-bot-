from typing import Any, Dict, List

AGENTS = ("market", "value", "risk", "tempo", "memory", "contradiction")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def settled_with_votes(db: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for scan in db.get("scans", {}).values():
        for pick in scan.get("picks", []):
            if pick.get("result") in ("win", "loss") and isinstance(pick.get("agent_votes"), dict):
                rows.append(pick)
    return rows


def learn_agent_weights(db: Dict[str, Any]) -> Dict[str, float]:
    rows = settled_with_votes(db)
    raw = {agent: {"score": 0.0, "n": 0} for agent in AGENTS}

    for pick in rows:
        won = pick.get("result") == "win"
        for agent in AGENTS:
            vote = (pick.get("agent_votes", {}).get(agent, {}) or {}).get("vote", "WATCHLIST")
            if vote == "ACCEPT":
                delta = 1.0 if won else -1.0
            elif vote == "WATCHLIST":
                delta = 0.20 if won else -0.10
            elif vote == "REJECT":
                delta = -0.70 if won else 0.70
            else:
                delta = 0.0
            raw[agent]["score"] += delta
            raw[agent]["n"] += 1

    weights = {}
    for agent, stat in raw.items():
        n = stat["n"]
        if n < 8:
            weights[agent] = 1.0
        else:
            avg = stat["score"] / max(1, n)
            weights[agent] = round(clamp(1.0 + avg * 0.35, 0.70, 1.30), 2)

    db["agent_weights"] = weights
    db["agent_weight_samples"] = len(rows)
    return weights


def vote_score(votes: Dict[str, Dict[str, Any]], weights: Dict[str, float]) -> float:
    total = 0.0
    for agent in AGENTS:
        total += num((votes.get(agent) or {}).get("score")) * num(weights.get(agent, 1.0), 1.0)
    return round(total, 2)


def explain_weights(weights: Dict[str, float]) -> str:
    return "\n".join(f"• {agent}: {weight}" for agent, weight in weights.items())
