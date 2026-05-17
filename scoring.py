from typing import Dict, List
from store import league_bucket, odds_bucket
from utils import clamp


def norm2(a, b):
    pa, pb = 1 / a, 1 / b
    s = pa + pb
    return pa / s, pb / s


def norm3(a, b, c):
    pa, pb, pc = 1 / a, 1 / b, 1 / c
    s = pa + pb + pc
    return pa / s, pb / s, pc / s


def candidates(match: Dict) -> List[Dict]:
    out = []
    if match.get("h2h_home") and match.get("h2h_draw") and match.get("h2h_away"):
        ph, pd, pa = norm3(float(match["h2h_home"]), float(match["h2h_draw"]), float(match["h2h_away"]))
        out += [
            {"type": "h2h", "pari": f"Victoire {match['home']}", "odds": float(match["h2h_home"]), "market_prob": ph},
            {"type": "draw", "pari": "Match nul", "odds": float(match["h2h_draw"]), "market_prob": pd},
            {"type": "h2h", "pari": f"Victoire {match['away']}", "odds": float(match["h2h_away"]), "market_prob": pa},
        ]
    if match.get("over25") and match.get("under25"):
        po, pu = norm2(float(match["over25"]), float(match["under25"]))
        out += [
            {"type": "total", "pari": "Plus de 2.5 buts", "odds": float(match["over25"]), "market_prob": po},
            {"type": "total", "pari": "Moins de 2.5 buts", "odds": float(match["under25"]), "market_prob": pu},
        ]
    if match.get("btts_yes") and match.get("btts_no"):
        py, pn = norm2(float(match["btts_yes"]), float(match["btts_no"]))
        out += [
            {"type": "btts", "pari": "Les deux équipes marquent - Oui", "odds": float(match["btts_yes"]), "market_prob": py},
            {"type": "btts", "pari": "Les deux équipes marquent - Non", "odds": float(match["btts_no"]), "market_prob": pn},
        ]
    for x in out:
        x["match_id"] = match["id"]
    return [x for x in out if 1.35 <= x["odds"] <= 4.5]


def learning_adjustment(match: Dict, cand: Dict, db: Dict) -> float:
    prof = db.get("learning", {})
    if prof.get("samples", 0) < 20:
        return 0.0
    adj = 0.0
    keys = [("by_market", cand["type"]), ("by_odds", odds_bucket(cand["odds"])), ("by_league", league_bucket(match["competition"]))]
    for section, key in keys:
        st = prof.get(section, {}).get(key)
        if st and st.get("n", 0) >= 8:
            adj += clamp(float(st.get("roi", 0)) / 100 * 10, -6, 6)
    return round(adj, 2)


def pre_score(match: Dict, cand: Dict, db: Dict) -> float:
    odds, prob, typ = cand["odds"], cand["market_prob"], cand["type"]
    score = 100 * prob + max(0, odds - 1.55) * 7
    score += 9 if typ in ("total", "btts") else -5 if typ == "draw" else -4
    score += 8 if 1.6 <= odds <= 2.25 else -12 if odds >= 3.2 else 0
    score -= {"major": 0, "other": 4, "volatile": 9}[league_bucket(match["competition"])]
    score += learning_adjustment(match, cand, db)
    return round(score, 2)


def market_pool(matches: List[Dict], db: Dict) -> List[Dict]:
    rows = []
    for match in matches:
        for cand in candidates(match):
            rows.append({"match": match, "candidate": cand, "prefilter_score": pre_score(match, cand, db)})
    return sorted(rows, key=lambda x: x["prefilter_score"], reverse=True)


def score_pick(match: Dict, cand: Dict, prefilter: float, db: Dict) -> Dict:
    odds, prob, typ = cand["odds"], cand["market_prob"], cand["type"]
    fused = clamp(prob + (0.035 if typ in ("total", "btts") else 0.015 if typ == "h2h" else 0.005), 0.34, 0.72)
    edge = fused - prob
    danger = 25 + {"major": 0, "other": 4, "volatile": 9}[league_bucket(match["competition"])]
    danger += 14 if typ == "draw" else 7 if typ == "h2h" else 2
    danger += 16 if odds >= 3.2 else 8 if odds >= 2.7 else 5 if odds >= 2.25 else 0
    adj = learning_adjustment(match, cand, db)
    conf = int(clamp(round(50 + fused * 34 + edge * 45 - danger * 0.10 + adj * 0.3), 52, 78))
    if odds >= 3.2:
        conf = min(conf, 60)
    ev = fused * odds - 1
    value = ev * 100 + edge * 60 + (8 if typ in ("total", "btts") else 0) + prefilter * 0.08 - danger * 0.12 + adj - (18 if odds >= 3.2 else 0)
    stake = 1 if odds >= 3.2 else 2 if conf >= 64 and danger < 66 else 1
    return {"confidence": conf, "danger": int(danger), "value_score": round(value, 2), "ev_pct": round(ev * 100, 1), "p_market": round(prob * 100, 1), "p_fused": round(fused * 100, 1), "edge_pct": round(edge * 100, 1), "stake_pct": stake, "learning_adj": adj}
