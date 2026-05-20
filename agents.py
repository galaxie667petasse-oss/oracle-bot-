from typing import Any, Dict, List, Tuple
from calibration import league_bucket, odds_bucket, segment_adjustment_for_pick

AGENTS = ("marche", "valeur", "risque", "rythme", "memoire", "contradiction")
AGENT_LABELS = {
    "marche": "Marché",
    "valeur": "Valeur",
    "risque": "Risque",
    "rythme": "Rythme",
    "memoire": "Mémoire",
    "contradiction": "Contradiction",
}
OLD_AGENT_MAP = {"market": "marche", "value": "valeur", "risk": "risque", "tempo": "rythme", "memory": "memoire", "contradiction": "contradiction"}


def _num(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def normalize_vote(vote: Any) -> str:
    vote = str(vote or "SURVEILLANCE").upper()
    return {"ACCEPT": "ACCEPTE", "WATCHLIST": "SURVEILLANCE", "REJECT": "REFUSE"}.get(vote, vote)


def _record_key(p: Dict[str, Any]) -> tuple:
    try:
        odds = round(float(p.get("odds", 0) or 0), 4)
    except Exception:
        odds = 0
    return (p.get("match_id"), p.get("home"), p.get("away"), p.get("pari"), p.get("market_type"), p.get("date_key"), odds)


def _scan_records(scan: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    rows.extend(scan.get("picks", []) or [])
    rows.extend(scan.get("candidates", []) or [])
    seen = set()
    unique = []
    for p in rows:
        key = _record_key(p)
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def heuristic_agent_votes(p: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    odds = _num(p.get("odds"), 2.0)
    typ = p.get("market_type", "")
    bucket = odds_bucket(odds)
    league = league_bucket(p.get("competition", ""))
    result = p.get("result")
    elo_diff = _num(p.get("elo_diff"), 0.0)

    market_score = 1 if bucket in ("low", "mid") else -1 if bucket == "very_high" else 0
    if typ == "draw":
        market_score -= 1
    if typ == "h2h" and odds > 3.2:
        market_score -= 1

    value_score = 0
    if result == "win" and odds >= 1.65:
        value_score += 1
    if result == "loss" and odds >= 2.3:
        value_score -= 1
    if typ == "h2h" and abs(elo_diff) >= 80 and odds <= 2.6:
        value_score += 1

    risk_score = 1 if bucket == "low" else 0 if bucket == "mid" else -1 if bucket == "high" else -2
    if typ == "draw":
        risk_score -= 1
    if league == "volatile":
        risk_score -= 1

    rhythm_score = 1 if typ in ("total", "btts") else -1 if typ == "draw" else 0
    memory_score = 1 if result == "win" and bucket == "low" else -1 if result == "loss" and bucket in ("high", "very_high") else 0
    contradiction_score = -2 if odds >= 3.5 else -1 if typ == "draw" else 0

    def vote(score: int) -> str:
        return "ACCEPTE" if score > 0 else "REFUSE" if score < 0 else "SURVEILLANCE"

    return {
        "marche": {"vote": vote(market_score), "score": market_score, "note": "vote historique généré par marché et cote"},
        "valeur": {"vote": vote(value_score), "score": value_score, "note": "vote historique généré par résultat, cote et Elo"},
        "risque": {"vote": vote(risk_score), "score": risk_score, "note": "vote historique généré par tranche de cote et ligue"},
        "rythme": {"vote": vote(rhythm_score), "score": rhythm_score, "note": "vote historique généré par type de marché"},
        "memoire": {"vote": vote(memory_score), "score": memory_score, "note": "vote historique généré par résultat observé"},
        "contradiction": {"vote": vote(contradiction_score), "score": contradiction_score, "note": "vote historique généré par prudence"},
    }


def ensure_agent_votes(p: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    votes = p.get("agent_votes")
    if not isinstance(votes, dict) or not votes:
        votes = heuristic_agent_votes(p)
        p["agent_votes"] = votes
        p["agent_votes_generated"] = True
    p.setdefault("agent_accepts", sum(1 for v in votes.values() if normalize_vote((v or {}).get("vote")) == "ACCEPTE"))
    p.setdefault("agent_rejects", sum(1 for v in votes.values() if normalize_vote((v or {}).get("vote")) == "REFUSE"))
    p.setdefault("council_score", round(sum(_num((v or {}).get("score")) for v in votes.values()), 2))
    return votes


def agent_outcome_counts(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    counts = {a: {"right": 0, "wrong": 0} for a in AGENTS}
    for p in rows:
        result = p.get("result")
        if result not in ("win", "loss"):
            continue
        votes = ensure_agent_votes(p)
        for old, new in OLD_AGENT_MAP.items():
            if old in votes and new not in votes:
                votes[new] = votes[old]
        for agent in AGENTS:
            vote = normalize_vote((votes.get(agent, {}) or {}).get("vote"))
            if vote not in ("ACCEPTE", "REFUSE"):
                continue
            right = (vote == "ACCEPTE" and result == "win") or (vote == "REFUSE" and result == "loss")
            counts[agent]["right" if right else "wrong"] += 1
    return counts


def agent_weights(db: Dict[str, Any]) -> Dict[str, float]:
    rows = [
        p
        for scan in db.get("scans", {}).values()
        for p in _scan_records(scan)
        if p.get("result") in ("win", "loss")
    ]
    raw = {a: {"score": 0.0, "n": 0} for a in AGENTS}
    for p in rows:
        won = p.get("result") == "win"
        votes = ensure_agent_votes(p)
        for old, new in OLD_AGENT_MAP.items():
            if old in votes and new not in votes:
                votes[new] = votes[old]
        for a in AGENTS:
            vote = normalize_vote((votes.get(a, {}) or {}).get("vote"))
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


def _memory_score(prof: Dict[str, Any], typ: str, odds: float, league: str) -> Tuple[int, List[str]]:
    score = 0
    notes = []
    if prof.get("samples", 0) < 20:
        notes.append(f"mémoire faible: {prof.get('samples',0)} résultats")
    checks = [
        ("by_market", typ, "marché", 2),
        ("by_odds", odds_bucket(odds), "cote", 1),
        ("by_league", league, "ligue", 1),
    ]
    for section, key, label, weight in checks:
        st = prof.get(section, {}).get(key)
        if not st:
            continue
        n = int(st.get("n", 0) or 0)
        roi = _num(st.get("roi"))
        if n >= 8 and roi < -8:
            score -= weight
            notes.append(f"{label} {key}: ROI {roi}% sur {n}")
        elif n >= 20 and roi > 8:
            score += weight
            notes.append(f"{label} {key}: ROI {roi}% sur {n}")
    return score, notes


def council(p: Dict[str, Any], db: Dict[str, Any]) -> Dict[str, Any]:
    ev, value, conf, danger, edge, odds = (_num(p.get(k)) for k in ("ev_pct", "value_score", "confidence", "danger", "edge_pct", "odds"))
    typ = p.get("market_type", "")
    lg = league_bucket(p.get("competition", ""))
    bucket = odds_bucket(odds)
    calibration = db.get("calibration", {}) or {}
    segment = segment_adjustment_for_pick(p, db)
    segment_adj = _num(segment.get("adjustment"))
    segment_positive = bool(segment.get("positive_reliable"))
    segment_block = bool(segment.get("block_top"))
    market_risk = (calibration.get("banned_or_penalized_markets", {}) or {}).get(typ, {}) or {}
    bucket_risk = (calibration.get("banned_or_penalized_odds_buckets", {}) or {}).get(bucket, {}) or {}
    confidence_cap = (calibration.get("confidence_cap_by_bucket", {}) or {}).get(bucket)
    if segment_block:
        danger += 8
    elif segment_adj < 0:
        danger += 3
    elif segment_adj > 0:
        danger = max(0, danger - 2)
        conf += min(2, segment_adj * 2)
    if market_risk:
        danger += 6 if market_risk.get("block_top") else 3
    if bucket_risk:
        danger += 7 if bucket_risk.get("block_top") else 4
    if confidence_cap:
        conf = min(conf, _num(confidence_cap, conf))
    flags = outlier_flags(p)
    fair = fair_odds(_num(p.get("p_fused"), 0))
    votes = {}

    m_score = (2 if edge >= 2.5 else 1 if edge >= 1.0 else -1) + (1 if 1.55 <= odds <= 2.35 else 0) - (2 if odds >= 3.2 else 0)
    if flags:
        m_score -= 1
    if segment_block:
        m_score -= 2
    elif segment_adj < 0:
        m_score -= 1
    elif segment_adj > 0:
        m_score += 1
    if market_risk:
        m_score -= 2 if market_risk.get("block_top") else 1
    if bucket_risk:
        m_score -= 2 if bucket_risk.get("block_top") else 1
    market_note = f"écart {edge}% · cote juste estimée {fair}"
    if market_risk or bucket_risk:
        market_note += " · historique défavorable"
    if segment.get("n"):
        market_note += f" · segment {segment.get('roi')}% sur {segment.get('n')}"
    votes["marche"] = {"vote": "ACCEPTE" if m_score >= 2 else "SURVEILLANCE" if m_score >= 0 else "REFUSE", "score": m_score, "note": market_note}

    v_score = (3 if ev >= 2 else 2 if ev >= 0.8 else 1 if ev >= 0 else -3) + (1 if value >= 4 else -1 if value < 0 else 0)
    if ev >= 25 and odds >= 3.2:
        v_score -= 2
    if segment_block:
        v_score -= 2
    elif segment_adj < 0:
        v_score -= 1
    elif segment_adj > 0:
        v_score += 0.5
    if market_risk.get("block_top") or bucket_risk.get("block_top"):
        v_score -= 2
    elif market_risk or bucket_risk:
        v_score -= 1
    votes["valeur"] = {"vote": "ACCEPTE" if v_score >= 3 else "SURVEILLANCE" if v_score >= 0 else "REFUSE", "score": v_score, "note": f"EV {ev}% · valeur {value}"}

    r_score = (2 if danger <= 38 else 1 if danger <= 55 else -2) - (2 if typ == "draw" else 1 if typ == "h2h" else 0) - (2 if lg == "volatile" else 0) - (2 if odds >= 3.5 else 1 if odds >= 2.8 else 0)
    if flags:
        r_score -= 1
    if segment_block:
        r_score -= 2
    elif segment_adj < 0:
        r_score -= 1
    elif segment_adj > 0:
        r_score += 0.5
    if market_risk:
        r_score -= 2 if market_risk.get("block_top") else 1
    if bucket_risk:
        r_score -= 2 if bucket_risk.get("block_top") else 1
    votes["risque"] = {"vote": "ACCEPTE" if r_score >= 2 else "SURVEILLANCE" if r_score >= 0 else "REFUSE", "score": r_score, "note": f"danger {danger}% · famille ligue {lg}"}

    t_score = (2 if typ in ("btts", "total") else -1 if typ == "h2h" else 0) + (1 if conf >= 66 else 0)
    votes["rythme"] = {"vote": "ACCEPTE" if t_score >= 2 else "SURVEILLANCE" if t_score >= 0 else "REFUSE", "score": t_score, "note": "marché buts préféré" if typ in ("btts", "total") else "victoire simple moins prioritaire"}

    prof = db.get("learning", {})
    mem_score, notes = _memory_score(prof, typ, odds, lg)
    if market_risk:
        mem_score -= 2 if market_risk.get("block_top") else 1
        notes.append(f"{typ}: ROI historique {market_risk.get('roi')}%")
    if bucket_risk:
        mem_score -= 2 if bucket_risk.get("block_top") else 1
        notes.append(f"{bucket}: ROI historique {bucket_risk.get('roi')}%")
    if segment.get("n"):
        mem_score += segment_adj
        notes.append(f"segment {segment.get('label')}: ROI {segment.get('roi')}% sur {segment.get('n')}")
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
    if segment_block:
        c_score -= 2
        reasons.append("segment historique à bloquer")
    elif segment_adj < 0:
        c_score -= 1
        reasons.append("segment historique défavorable")
    votes["contradiction"] = {"vote": "ACCEPTE" if c_score >= 1 else "SURVEILLANCE" if c_score >= -2 else "REFUSE", "score": c_score, "note": ", ".join(reasons) or "pas d'alerte majeure"}

    weights = db.get("agent_weights") or agent_weights(db)
    weighted = round(sum(votes[a]["score"] * weights.get(a, 1.0) for a in AGENTS), 2)
    accepts = sum(1 for v in votes.values() if v["vote"] == "ACCEPTE")
    rejects = sum(1 for v in votes.values() if v["vote"] == "REFUSE")

    high_h2h = typ == "h2h" and odds > 3.50
    min_ev_top = _num(calibration.get("min_ev_for_top"), 1.0)
    min_score_top = _num(calibration.get("min_council_score_for_top"), 6.5)
    max_danger_top = _num(calibration.get("max_danger_for_top"), 58)
    max_h2h_top = _num(calibration.get("max_h2h_odds_for_top"), 3.2)
    max_draw_top = _num(calibration.get("max_draw_odds_for_top"), 3.2)
    max_obs_negative = _num(calibration.get("max_observation_negative_score"), -6.0)
    if ev < 0:
        decision, stake = ("SURVEILLANCE", 0) if conf >= 64 and danger <= 42 and weighted >= 1.5 and rejects <= 1 else ("REFUSE", 0)
    elif high_h2h:
        decision, stake = ("SURVEILLANCE", 0) if weighted >= 4.0 and rejects <= 1 and mem_score >= 1 else ("REFUSE", 0)
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
    draw_stats = (calibration.get("by_market", {}) or {}).get("draw", {}) or {}
    draw_memory_positive = int(draw_stats.get("n", 0) or 0) >= 100 and _num(draw_stats.get("roi")) > 3
    h2h_segment_positive = typ == "h2h" and segment_positive
    draw_segment_positive = typ == "draw" and segment_positive
    very_high_block = bucket == "very_high" and bool(bucket_risk.get("block_top"))
    market_block = bool(market_risk.get("block_top")) and not (h2h_segment_positive or draw_segment_positive)
    bucket_block = bool(bucket_risk.get("block_top")) and not (segment_positive and bucket != "very_high")
    block_top = bool(segment_block or very_high_block or market_block or bucket_block)
    if decision == "ACCEPTE":
        top_blocked = (
            ev < min_ev_top
            or weighted < min_score_top
            or danger > max_danger_top
            or block_top
            or (typ == "h2h" and odds > max_h2h_top and not h2h_segment_positive)
            or (typ == "draw" and not draw_segment_positive and (not draw_memory_positive or max_draw_top <= 0 or odds > max_draw_top))
        )
        if top_blocked:
            decision, stake = ("SURVEILLANCE", 0) if weighted >= max_obs_negative and rejects <= 2 else ("REFUSE", 0)
    if decision == "SURVEILLANCE" and weighted < max_obs_negative:
        decision, stake = "REFUSE", 0
    grade = "A" if decision == "ACCEPTE" and conf >= 68 and danger <= 45 and ev >= 1.5 else "B+" if decision == "ACCEPTE" else "B-" if decision == "SURVEILLANCE" else "C"
    summary = "Signal intéressant, conservé en observation." if decision == "SURVEILLANCE" else "Signal accepté par le conseil, à suivre avec prudence." if decision == "ACCEPTE" else "Marché refusé par prudence."
    if flags:
        summary += " Alerte: " + ", ".join(flags) + "."
    return {
        "decision": decision,
        "confidence": int(conf),
        "danger": int(danger),
        "council_score": weighted,
        "agent_votes": votes,
        "agent_accepts": accepts,
        "agent_rejects": rejects,
        "agent_weights": weights,
        "stake_pct": stake,
        "quality": grade,
        "fair_odds": fair,
        "outlier_flags": flags,
        "resume": summary,
        "segment_key": segment.get("segment_key", ""),
        "segment_label": segment.get("label", ""),
        "segment_roi": segment.get("roi", 0),
        "segment_n": segment.get("n", 0),
        "segment_note": segment.get("note", "neutre"),
        "calibration_max_observation_negative_score": max_obs_negative,
    }


def _keep_observation(p: Dict[str, Any]) -> bool:
    score = _num(p.get("council_score"))
    ev = _num(p.get("ev_pct"))
    rejects = int(p.get("agent_rejects", 0) or 0)
    odds = _num(p.get("odds"), 2.0)
    flags = p.get("outlier_flags") or []
    max_negative = _num(p.get("calibration_max_observation_negative_score"), -6.0)
    if score < max_negative:
        return False
    if score >= 0 and rejects <= 2:
        return True
    if ev >= 15 and rejects <= 3 and odds <= 4.2 and score >= max_negative:
        return True
    if flags and score < max_negative:
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
