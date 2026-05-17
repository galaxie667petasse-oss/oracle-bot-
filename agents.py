from typing import Any, Dict, List, Tuple
from store import odds_bucket, league_bucket

AGENTS = ("market", "value", "risk", "tempo", "memory", "contradiction")


def _num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def agent_weights(db: Dict[str, Any]) -> Dict[str, float]:
    rows = [
        p
        for scan in db.get("scans", {}).values()
        for p in scan.get("picks", [])
        if p.get("result") in ("win", "loss") and isinstance(p.get("agent_votes"), dict)
    ]
    raw = {a: {"score": 0.0, "n": 0} for a in AGENTS}
    for p in rows:
        won = p.get("result") == "win"
        for a in AGENTS:
            vote = (p.get("agent_votes", {}).get(a, {}) or {}).get("vote", "WATCHLIST")
            if vote == "ACCEPT":
                delta = 1.0 if won else -1.0
            elif vote == "REJECT":
                delta = -0.7 if won else 0.7
            else:
                delta = 0.2 if won else -0.1
            raw[a]["score"] += delta
            raw[a]["n"] += 1
    weights = {}
    for a, st in raw.items():
        if st["n"] < 8:
            weights[a] = 1.0
        else:
            weights[a] = round(max(0.70, min(1.30, 1.0 + (st["score"] / max(1, st["n"])) * 0.35)), 2)
    db["agent_weights"] = weights
    db["agent_weight_samples"] = len(rows)
    return weights


def council(p: Dict[str, Any], db: Dict[str, Any]) -> Dict[str, Any]:
    ev, value, conf, danger, edge, odds = (_num(p.get(k)) for k in ("ev_pct", "value_score", "confidence", "danger", "edge_pct", "odds"))
    typ = p.get("market_type", "")
    lg = league_bucket(p.get("competition", ""))
    votes = {}

    m_score = (2 if edge >= 2.5 else 1 if edge >= 1.0 else -1) + (1 if 1.55 <= odds <= 2.35 else 0) - (2 if odds >= 3.2 else 0)
    votes["market"] = {"vote": "ACCEPT" if m_score >= 2 else "WATCHLIST" if m_score >= 0 else "REJECT", "score": m_score, "note": f"edge {edge}% / cote {odds}"}

    v_score = (3 if ev >= 2 else 2 if ev >= 0.5 else 1 if ev >= 0 else -3) + (1 if value >= 4 else -1 if value < 0 else 0)
    votes["value"] = {"vote": "ACCEPT" if v_score >= 3 else "WATCHLIST" if v_score >= 0 else "REJECT", "score": v_score, "note": f"EV {ev}% / value {value}"}

    r_score = (2 if danger <= 38 else 1 if danger <= 55 else -2) - (2 if typ == "draw" else 1 if typ == "h2h" else 0) - (2 if lg == "volatile" else 0) - (1 if odds >= 2.8 else 0)
    votes["risk"] = {"vote": "ACCEPT" if r_score >= 2 else "WATCHLIST" if r_score >= 0 else "REJECT", "score": r_score, "note": f"danger {danger}% / ligue {lg}"}

    t_score = (2 if typ in ("btts", "total") else -1 if typ == "h2h" else 0) + (1 if conf >= 66 else 0)
    votes["tempo"] = {"vote": "ACCEPT" if t_score >= 2 else "WATCHLIST" if t_score >= 0 else "REJECT", "score": t_score, "note": "marchés buts favorisés" if typ in ("btts", "total") else "H2H moins prioritaire"}

    prof = db.get("learning", {})
    mem_score = 0
    notes = []
    if prof.get("samples", 0) < 20:
        notes.append(f"{prof.get('samples',0)} samples")
    for section, key in [("by_market", typ), ("by_odds", odds_bucket(odds)), ("by_league", lg)]:
        st = prof.get(section, {}).get(key)
        if st and st.get("n", 0) >= 8:
            roi = _num(st.get("roi"))
            mem_score += 1 if roi > 8 else -1 if roi < -8 else 0
            notes.append(f"{key} ROI {roi}%")
    votes["memory"] = {"vote": "ACCEPT" if mem_score >= 2 else "WATCHLIST" if mem_score >= -1 else "REJECT", "score": mem_score, "note": "; ".join(notes) or "neutre"}

    c_score = 1
    reasons = []
    if ev < 0:
        c_score -= 3
        reasons.append("EV négative")
    if typ == "h2h" and edge < 2:
        c_score -= 1
        reasons.append("H2H edge faible")
    if danger > 55:
        c_score -= 2
        reasons.append("danger élevé")
    votes["contradiction"] = {"vote": "ACCEPT" if c_score >= 1 else "WATCHLIST" if c_score >= -2 else "REJECT", "score": c_score, "note": ", ".join(reasons) or "pas de contradiction forte"}

    weights = db.get("agent_weights") or agent_weights(db)
    weighted = round(sum(votes[a]["score"] * weights.get(a, 1.0) for a in AGENTS), 2)
    accepts = sum(1 for v in votes.values() if v["vote"] == "ACCEPT")
    rejects = sum(1 for v in votes.values() if v["vote"] == "REJECT")

    if ev < 0:
        decision, stake = ("WATCHLIST", 0) if conf >= 64 and danger <= 42 and weighted >= 1.5 and rejects <= 1 else ("REJECT", 0)
    elif ev < 0.8:
        decision, stake = ("WATCHLIST", 0) if weighted >= 2.0 and rejects <= 1 else ("REJECT", 0)
    elif weighted >= 6.5 and accepts >= 3 and rejects == 0 and conf >= 60 and danger <= 58:
        decision, stake = "ACCEPT", (1 if ev < 2 else min(int(p.get("stake_pct", 1) or 1), 2))
    elif weighted >= 1.5 and rejects <= 2 and conf >= 56:
        decision, stake = "WATCHLIST", 0
    else:
        decision, stake = "REJECT", 0
    grade = "A" if decision == "ACCEPT" and conf >= 68 and danger <= 45 and ev >= 1.5 else "B+" if decision == "ACCEPT" else "B-" if decision == "WATCHLIST" else "C"
    return {"decision": decision, "council_score": weighted, "agent_votes": votes, "agent_accepts": accepts, "agent_rejects": rejects, "agent_weights": weights, "stake_pct": stake, "quality": grade}


def select_picks(rows: List[Dict[str, Any]], top_limit: int, watch_limit: int) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    rows = sorted(rows, key=lambda p: (p.get("decision") == "ACCEPT", p.get("council_score", 0), p.get("ev_pct", -99), p.get("value_score", -99) - 0.2 * p.get("danger", 50)), reverse=True)
    top, watch, reject, seen = [], [], [], set()
    h2h = 0
    for p in rows:
        if p["match_id"] in seen:
            continue
        if p["decision"] == "ACCEPT":
            if p["market_type"] == "h2h" and h2h >= 1:
                watch.append(p); seen.add(p["match_id"]); continue
            top.append(p); seen.add(p["match_id"])
            h2h += p["market_type"] == "h2h"
            if len(top) >= top_limit:
                break
    for p in rows:
        if p["match_id"] in seen:
            continue
        if p["decision"] == "WATCHLIST":
            watch.append(p); seen.add(p["match_id"])
        else:
            reject.append(p)
    return top[:top_limit], watch[:watch_limit], reject
