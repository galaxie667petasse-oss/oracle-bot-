from typing import Any, Dict, List, Tuple
from store import odds_bucket, league_bucket

AGENTS = ("marche", "valeur", "risque", "rythme", "memoire", "contradiction")
OLD_AGENT_MAP = {"market": "marche", "value": "valeur", "risk": "risque", "tempo": "rythme", "memory": "memoire", "contradiction": "contradiction"}


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
        votes = p.get("agent_votes", {}) or {}
        for old, new in OLD_AGENT_MAP.items():
            if old in votes and new not in votes:
                votes[new] = votes[old]
        for a in AGENTS:
            vote = (votes.get(a, {}) or {}).get("vote", "SURVEILLANCE")
            vote = {"ACCEPT": "ACCEPTE", "WATCHLIST": "SURVEILLANCE", "REJECT": "REFUSE"}.get(vote, vote)
            if vote == "ACCEPTE":
                delta = 1.0 if won else -1.0
            elif vote == "REFUSE":
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


def fair_odds(prob_pct: float) -> float:
    prob = max(0.01, prob_pct / 100)
    return round(1 / prob, 2)


def outlier_flags(p: Dict[str, Any]) -> List[str]:
    odds = _num(p.get("odds"), 2.0)
    edge = _num(p.get("edge_pct"))
    ev = _num(p.get("ev_pct"))
    typ = p.get("market_type", "")
    flags = []
    if odds >= 3.50:
        flags.append("cote très haute")
    if typ == "h2h" and odds >= 2.80:
        flags.append("victoire simple outsider")
    if ev >= 25 and odds >= 3.20:
        flags.append("EV énorme à confirmer")
    if edge >= 9 and odds >= 3.20:
        flags.append("écart modèle/marché brutal")
    return flags


def council(p: Dict[str, Any], db: Dict[str, Any]) -> Dict[str, Any]:
    ev, value, conf, danger, edge, odds = (_num(p.get(k)) for k in ("ev_pct", "value_score", "confidence", "danger", "edge_pct", "odds"))
    typ = p.get("market_type", "")
    lg = league_bucket(p.get("competition", ""))
    flags = outlier_flags(p)
    fair = fair_odds(_num(p.get("p_fused"), 0))
    votes = {}

    m_score = (2 if edge >= 2.5 else 1 if edge >= 1.0 else -1) + (1 if 1.55 <= odds <= 2.35 else 0) - (2 if odds >= 3.2 else 0)
    if flags:
        m_score -= 1
    votes["marche"] = {"vote": "ACCEPTE" if m_score >= 2 else "SURVEILLANCE" if m_score >= 0 else "REFUSE", "score": m_score, "note": f"écart {edge}% · cote juste estimée {fair}"}

    v_score = (3 if ev >= 2 else 2 if ev >= 0.8 else 1 if ev >= 0 else -3) + (1 if value >= 4 else -1 if value < 0 else 0)
    if ev >= 25 and odds >= 3.2:
        v_score -= 2
    votes["valeur"] = {"vote": "ACCEPTE" if v_score >= 3 else "SURVEILLANCE" if v_score >= 0 else "REFUSE", "score": v_score, "note": f"EV {ev}% · valeur {value}"}

    r_score = (2 if danger <= 38 else 1 if danger <= 55 else -2) - (2 if typ == "draw" else 1 if typ == "h2h" else 0) - (2 if lg == "volatile" else 0) - (2 if odds >= 3.5 else 1 if odds >= 2.8 else 0)
    if flags:
        r_score -= 1
    votes["risque"] = {"vote": "ACCEPTE" if r_score >= 2 else "SURVEILLANCE" if r_score >= 0 else "REFUSE", "score": r_score, "note": f"danger {danger}% · famille ligue {lg}"}

    t_score = (2 if typ in ("btts", "total") else -1 if typ == "h2h" else 0) + (1 if conf >= 66 else 0)
    votes["rythme"] = {"vote": "ACCEPTE" if t_score >= 2 else "SURVEILLANCE" if t_score >= 0 else "REFUSE", "score": t_score, "note": "marché buts préféré" if typ in ("btts", "total") else "victoire simple moins prioritaire"}

    prof = db.get("learning", {})
    mem_score = 0
    notes = []
    if prof.get("samples", 0) < 20:
        notes.append(f"mémoire faible: {prof.get('samples',0)} résultats")
    for section, key in [("by_market", typ), ("by_odds", odds_bucket(odds)), ("by_league", lg)]:
        st = prof.get(section, {}).get(key)
        if st and st.get("n", 0) >= 8:
            roi = _num(st.get("roi"))
            mem_score += 1 if roi > 8 else -1 if roi < -8 else 0
            notes.append(f"{key}: ROI {roi}%")
    votes["memoire"] = {"vote": "ACCEPTE" if mem_score >= 2 else "SURVEILLANCE" if mem_score >= -1 else "REFUSE", "score": mem_score, "note": "; ".join(notes) or "mémoire neutre"}

    c_score = 1
    reasons = []
    if ev < 0:
        c_score -= 3
        reasons.append("EV négative")
    if typ == "h2h" and edge < 2:
        c_score -= 1
        reasons.append("H2H peu différenciant")
    if odds >= 3.5:
        c_score -= 2
        reasons.append("cote outsider")
    if danger > 55:
        c_score -= 2
        reasons.append("danger élevé")
    votes["contradiction"] = {"vote": "ACCEPTE" if c_score >= 1 else "SURVEILLANCE" if c_score >= -2 else "REFUSE", "score": c_score, "note": ", ".join(reasons) or "pas d'alerte majeure"}

    weights = db.get("agent_weights") or agent_weights(db)
    weighted = round(sum(votes[a]["score"] * weights.get(a, 1.0) for a in AGENTS), 2)
    accepts = sum(1 for v in votes.values() if v["vote"] == "ACCEPTE")
    rejects = sum(1 for v in votes.values() if v["vote"] == "REFUSE")

    if ev < 0:
        decision, stake = ("SURVEILLANCE", 0) if conf >= 64 and danger <= 42 and weighted >= 1.5 and rejects <= 1 else ("REFUSE", 0)
    elif flags and odds >= 3.5:
        decision, stake = ("SURVEILLANCE", 0)
    elif ev < 0.8:
        decision, stake = ("SURVEILLANCE", 0) if weighted >= 2.0 and rejects <= 1 else ("REFUSE", 0)
    elif weighted >= 6.5 and accepts >= 3 and rejects == 0 and conf >= 60 and danger <= 58:
        decision, stake = "ACCEPTE", (1 if ev < 2 else min(int(p.get("stake_pct", 1) or 1), 2))
    elif weighted >= 1.5 and rejects <= 2 and conf >= 56:
        decision, stake = "SURVEILLANCE", 0
    else:
        decision, stake = "REFUSE", 0
    grade = "A" if decision == "ACCEPTE" and conf >= 68 and danger <= 45 and ev >= 1.5 else "B+" if decision == "ACCEPTE" else "B-" if decision == "SURVEILLANCE" else "C"
    summary = "Signal intéressant mais pas assez confirmé." if decision == "SURVEILLANCE" else "Pick accepté par le conseil." if decision == "ACCEPTE" else "Marché refusé par prudence."
    if flags:
        summary += " Alerte: " + ", ".join(flags) + "."
    return {"decision": decision, "council_score": weighted, "agent_votes": votes, "agent_accepts": accepts, "agent_rejects": rejects, "agent_weights": weights, "stake_pct": stake, "quality": grade, "fair_odds": fair, "outlier_flags": flags, "resume": summary}


def _keep_observation(p: Dict[str, Any]) -> bool:
    score = _num(p.get("council_score"))
    ev = _num(p.get("ev_pct"))
    rejects = int(p.get("agent_rejects", 0) or 0)
    odds = _num(p.get("odds"), 2.0)
    flags = p.get("outlier_flags") or []
    if score >= 0 and rejects <= 2:
        return True
    if ev >= 15 and rejects <= 3 and odds <= 4.2 and score >= -6:
        return True
    if flags and score < -6:
        return False
    return False


def select_picks(rows: List[Dict[str, Any]], top_limit: int, watch_limit: int) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    rows = sorted(rows, key=lambda p: (p.get("decision") == "ACCEPTE", p.get("council_score", 0), p.get("ev_pct", -99), p.get("value_score", -99) - 0.2 * p.get("danger", 50)), reverse=True)
    top, watch, reject, seen = [], [], [], set()
    h2h = 0
    for p in rows:
        if p["match_id"] in seen:
            continue
        if p["decision"] == "ACCEPTE":
            if p["market_type"] == "h2h" and h2h >= 1:
                if _keep_observation(p):
                    watch.append(p)
                else:
                    reject.append(p)
                seen.add(p["match_id"])
                continue
            top.append(p); seen.add(p["match_id"])
            h2h += p["market_type"] == "h2h"
            if len(top) >= top_limit:
                break
    for p in rows:
        if p["match_id"] in seen:
            continue
        if p["decision"] == "SURVEILLANCE" and _keep_observation(p):
            watch.append(p); seen.add(p["match_id"])
        else:
            reject.append(p)
    return top[:top_limit], watch[:watch_limit], reject
