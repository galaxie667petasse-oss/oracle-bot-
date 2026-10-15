from __future__ import annotations

from datetime import date, datetime, timedelta

from v10.odds import proportional_no_vig
from v10.operations.freshness import PrematchFreshnessPolicy
from v10.statistics.dixon_coles import DixonColesModel
from v10.statistics.elo import EloModel
from v10.statistics.poisson import PoissonModel
from v10.statistics.types import HistoricalMatch
from v10.time import ensure_utc
from v11 import VERSION
from v11.contracts import Snapshot
from v11.ledger import Ledger, digest
from v11.markets import price
from v11.sources import FR_BOOKMAKER_KEYS


def historical_matches(snapshot: Snapshot, as_of: datetime, competition: str) -> list[HistoricalMatch]:
    return [HistoricalMatch(m.match_id, m.kickoff, m.competition, str(m.kickoff.year),
                            m.home, m.away, m.home_goals, m.away_goals, observed_at=m.result_observed_at)
            for m in sorted(snapshot.history, key=lambda m: (m.kickoff, m.match_id))
            if m.competition == competition and m.kickoff < as_of and m.result_observed_at <= as_of]


def analyze(ledger: Ledger, day: date, now: datetime, include_penaltyblog: bool = False) -> dict:
    ensure_utc(now)
    latest = ledger.latest_snapshot()
    if latest is None:
        return {"date": str(day), "status": "blocked", "reasons": ["no_source_snapshot"], "fixtures": []}
    snapshot_id, raw = latest
    snapshot = Snapshot.model_validate(raw)
    if snapshot.captured_at > now:
        raise ValueError("future snapshot cannot inform decision")
    results = []
    for fixture in snapshot.fixtures:
        if fixture.kickoff.date() != day:
            continue
        reasons = ["models_not_validated_for_recommendations"]
        if snapshot.provenance == "synthetic":
            reasons.append("synthetic_data")
        if fixture.kickoff <= now or fixture.status != "SCHEDULED":
            results.append({"fixture_id": fixture.fixture_id, "home": fixture.home, "away": fixture.away,
                            "decision": "ABSTAIN", "reasons": ["not_prematch"], "models": [], "comparisons": []})
            continue
        phase = "T10" if fixture.kickoff-now <= timedelta(minutes=10) else "T30" if fixture.kickoff-now <= timedelta(minutes=30) else "T90" if fixture.kickoff-now <= timedelta(minutes=90) else "T24"
        policy = PrematchFreshnessPolicy()
        if not timedelta(0) <= now-fixture.observed_at <= policy.rules(phase)["fixture"].max_age:
            reasons.append("fixture_stale_or_future")
        history = historical_matches(snapshot, now, fixture.competition)
        # Explicit membership required; team-name similarity is never a cross-provider join.
        teams = {t for m in history for t in (m.home_team, m.away_team)}
        if len(history) < 30 or not {fixture.home, fixture.away} <= teams:
            reasons.append("insufficient_team_history")
        predictions = []
        distributions = []
        model_errors = []
        if "insufficient_team_history" not in reasons:
            models = [PoissonModel(), DixonColesModel(), EloModel()]
            if include_penaltyblog:
                from v11.models import PenaltyblogAdapter
                models.extend(PenaltyblogAdapter(kind) for kind in PenaltyblogAdapter.classes)
            for model in models:
                try:
                    pred = model.fit(history).predict(fixture.home, fixture.away)
                    predictions.append(pred.to_dict())
                    if pred.score_distribution:
                        distributions.append(pred.score_distribution)
                except (ValueError, RuntimeError) as exc:
                    model_errors.append({"model": model.model_key, "error_type": type(exc).__name__})
        valid_quotes = []
        comparisons = []
        rejected = []
        for q in fixture.quotes:
            updated = q.provider_updated_at
            fresh = (updated is not None and timedelta(0) <= now-updated <= policy.odds_max_age(phase)
                     and timedelta(0) <= now-q.observed_at <= policy.odds_max_age(phase))
            if not fresh:
                rejected.append({**q.model_dump(mode="json"), "reason": "odds_stale_missing_or_future_timestamp"})
                continue
            valid_quotes.append(q)
            for distribution in distributions:
                comparisons.append({**q.model_dump(mode="json"), "model": distribution.model_key,
                                    **price(distribution, q.market, q.selection, q.odds, q.line),
                                    "uncertainty": None, "uncertainty_status": "not_estimated"})
        if not valid_quotes:
            reasons.append("no_fresh_odds")
        present_books = {q.bookmaker for q in valid_quotes}
        missing_books = [name for name, key in FR_BOOKMAKER_KEYS.items() if key not in present_books]
        if model_errors:
            reasons.append("model_errors")
        baselines = []
        books = sorted({(q.source, q.bookmaker) for q in valid_quotes})
        for source, book in books:
            group = [q for q in valid_quotes if q.source == source and q.bookmaker == book and q.market == "match_winner"]
            # Never remove margin from a synthetic set of best prices across books.
            if len(group) == 3 and {q.selection for q in group} == {"home", "draw", "away"}:
                baselines.append({"source": source, "bookmaker": book,
                                  "probabilities": proportional_no_vig({q.selection: q.odds for q in group})})
        payload = {"version": VERSION, "fixture_id": fixture.fixture_id, "home": fixture.home,
                   "away": fixture.away, "kickoff": fixture.kickoff.isoformat(), "decision_at": now.isoformat(),
                   "snapshot_id": snapshot_id, "source": fixture.source, "provenance": snapshot.provenance,
                   "training_count": len(history), "training_hash": digest({"matches": [m.to_dict() for m in history]}),
                   "training_cutoff": max((m.observed_at for m in history), default=None).isoformat() if history else None,
                   "models": predictions, "model_errors": model_errors, "comparisons": comparisons,
                   "market_baselines": baselines, "quotes": [q.model_dump(mode="json") for q in fixture.quotes],
                   "rejected_quotes": rejected, "decision": "ABSTAIN", "reasons": reasons,
                   "missing_bookmakers": missing_books,
                   "can_influence_picks": False}
        key = ledger.add_prediction(payload)
        results.append({"id": key, **payload})
    return {"date": str(day), "status": "research_only", "fixtures": results,
            "snapshot_id": snapshot_id, "captured_at": snapshot.captured_at.isoformat(),
            "provenance": snapshot.provenance, "can_influence_picks": False}
