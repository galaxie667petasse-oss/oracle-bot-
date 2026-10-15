"""Prespecified hypothetical selections, never a change to an ABSTAIN decision."""
from __future__ import annotations

from datetime import datetime, timedelta

from v11.contracts import Quote
from v11.evaluation import grouped_interval
from v11.markets import finite, settle


def paper_report(records: list[dict], model_key: str, min_ev: float = .05,
                 closing: dict[str, list[Quote]] | None = None) -> dict:
    finite(min_ev)
    if min_ev < 0 or not model_key:
        raise ValueError("explicit fixed model and nonnegative threshold required")
    provenances = sorted({r["provenance"] for r in records})
    if len(provenances) > 1:
        raise ValueError("evaluate synthetic, manual and real-provider evidence separately")
    # Earliest sealed analysis per fixture prevents selecting a favourable re-run.
    first = {}
    for record in sorted(records, key=lambda r: datetime.fromisoformat(r["decision_at"])):
        first.setdefault(record["fixture_id"], record)
    rows = []
    for record in first.values():
        decision = datetime.fromisoformat(record["decision_at"])
        kickoff = datetime.fromisoformat(record["kickoff"])
        candidates = [q for q in record.get("comparisons", [])
                      if q["model"] == model_key and q["expected_value"] >= min_ev
                      and q["market"] == "match_winner"]
        if not candidates or decision >= kickoff:
            continue
        q = sorted(candidates, key=lambda q: (-q["expected_value"], q["bookmaker"], q["selection"]))[0]
        outcomes = record.get("outcomes", [])
        final = outcomes[-1] if outcomes else None
        settlement = settle(q["market"], q["selection"], q["odds"], final["home"], final["away"],
                            q["line"], final["status"]) if final else None
        available = [c for c in (closing or {}).get(record["fixture_id"], [])
                     if (c.source,c.bookmaker,c.market,c.selection,c.line)==(q["source"],q["bookmaker"],q["market"],q["selection"],q["line"])
                     and decision < c.observed_at < kickoff and c.provider_updated_at is not None
                     and decision < c.provider_updated_at <= c.observed_at
                     and kickoff-c.provider_updated_at <= timedelta(hours=1)]
        close = max(available, key=lambda c: c.observed_at) if available else None
        rows.append({"fixture_id": record["fixture_id"], "prediction_id": record["id"], "day": str(kickoff.date()),
                     "bookmaker": q["bookmaker"], "selection": q["selection"], "odds": q["odds"],
                     "profit_units": settlement.profit_units if settlement else None,
                     "settlement": settlement.status if settlement else "pending",
                     "clv_odds_ratio": q["odds"]/close.odds-1 if close else None})
    settled = [r for r in rows if r["profit_units"] is not None and r["settlement"] != "void"]
    clv = [r["clv_odds_ratio"] for r in rows if r["clv_odds_ratio"] is not None]
    return {"status": "hypothetical_only", "policy": {"model": model_key, "min_ev": min_ev, "unit_stake": 1,
                                                       "market": "match_winner", "max_selections_per_fixture": 1},
            "provenances": provenances, "rows": rows, "settled_count": len(settled),
            "roi_simulated": sum(r["profit_units"] for r in settled)/len(settled) if settled else None,
            "roi_day_bootstrap_95": grouped_interval([(r["day"],r["profit_units"]) for r in settled]),
            "mean_clv_odds_ratio": sum(clv)/len(clv) if clv else None,
            "can_influence_picks": False,
            "limitations": ["Counterfactual unit-stake simulation of abstained analyses; no executed bets",
                            "No confidence interval with fewer than 10 distinct match days",
                            "Availability of the offered price on an actual account is unverified"]}
