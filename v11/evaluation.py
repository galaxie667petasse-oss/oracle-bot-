"""Fixed chronological folds, disjoint calibration, grouped uncertainty.

Requires result availability timestamps. Date-only imported archives cannot be
treated as timestamped prematch evidence. All evaluations remain research only.
"""
from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import timedelta

from v10.odds import proportional_no_vig
from v10.statistics.dixon_coles import DixonColesModel
from v10.statistics.elo import EloModel
from v10.statistics.metrics import multiclass_brier, multiclass_log_loss
from v10.statistics.poisson import PoissonModel
from v11.contracts import HistoryMatch, Quote
from v11.ledger import digest


def temperature(probabilities: dict[str, float], t: float) -> dict[str, float]:
    if t <= 0 or not math.isfinite(t):
        raise ValueError("positive finite temperature required")
    logits = {k: math.log(max(p, 1e-12))/t for k, p in probabilities.items()}
    peak = max(logits.values())
    exp = {k: math.exp(v-peak) for k, v in logits.items()}
    return {k: v/sum(exp.values()) for k, v in exp.items()}


def fit_temperature(probabilities: list[dict], labels: list[str]) -> float:
    if len(labels) < 30 or len(set(labels)) < 3:
        return 1.0
    return min([1.0] + [n/10 for n in range(5, 41)], key=lambda t: multiclass_log_loss(
        [temperature(p, t) for p in probabilities], labels))


def calibration_bins(probabilities: list[dict], labels: list[str]) -> list[dict]:
    bins = []
    for cls in ("home", "draw", "away"):
        for idx in range(10):
            pairs = [(p[cls], int(y == cls)) for p, y in zip(probabilities, labels)
                     if min(int(p[cls]*10), 9) == idx]
            bins.append({"class": cls, "low": idx/10, "high": (idx+1)/10, "count": len(pairs),
                         "mean_probability": sum(p for p, _ in pairs)/len(pairs) if pairs else None,
                         "frequency": sum(y for _, y in pairs)/len(pairs) if pairs else None})
    return bins


def grouped_interval(values: list[tuple[str, float]], repeats: int = 500) -> list[float] | None:
    groups = defaultdict(list)
    for group, value in values:
        groups[group].append(value)
    if len(groups) < 10:
        return None
    rng = random.Random(11)
    keys = sorted(groups)
    samples = []
    for _ in range(repeats):
        draw = [v for k in rng.choices(keys, k=len(keys)) for v in groups[k]]
        samples.append(sum(draw)/len(draw))
    samples.sort()
    return [samples[int(.025*repeats)], samples[min(int(.975*repeats), repeats-1)]]


def chronological_evaluation(matches: list[HistoryMatch], train_min: int = 80, test_size: int = 20,
                             calibration_size: int = 30, embargo: timedelta = timedelta(days=1),
                             archived_quotes: dict[str, list[Quote]] | None = None,
                             include_penaltyblog: bool = False) -> dict:
    from v10.statistics.types import HistoricalMatch
    if train_min < 10 or test_size < 1 or calibration_size < 0 or embargo < timedelta(0):
        raise ValueError("invalid chronological split configuration")
    if len({m.match_id for m in matches}) != len(matches):
        raise ValueError("duplicate matches")
    if len({m.competition for m in matches}) > 1:
        raise ValueError("evaluate each competition independently")
    ordered = sorted(matches, key=lambda m: (m.kickoff, m.match_id))
    folds, observations, errors = [], [], []
    start = train_min + calibration_size
    while start < len(ordered):
        # Keep simultaneous fixtures together; no fixture appears in two folds.
        end = min(start+test_size, len(ordered))
        while end < len(ordered) and ordered[end].kickoff == ordered[end-1].kickoff:
            end += 1
        test = ordered[start:end]
        decision_at = test[0].kickoff - timedelta(hours=2)
        cutoff = decision_at-embargo
        prior = [m for m in ordered[:start] if m.kickoff < cutoff and m.result_observed_at <= cutoff]
        calibration = prior[-calibration_size:] if calibration_size else []
        calibration_cutoff = calibration[0].kickoff-timedelta(hours=2)-embargo if calibration else cutoff
        train = [m for m in prior if m.kickoff < calibration_cutoff and m.result_observed_at <= calibration_cutoff]
        if len(train) < train_min:
            start = end
            continue
        history = [HistoricalMatch(m.match_id, m.kickoff, m.competition, str(m.kickoff.year), m.home, m.away,
                                   m.home_goals, m.away_goals, observed_at=m.result_observed_at) for m in train]
        model_list = [PoissonModel(), DixonColesModel(), EloModel()]
        if include_penaltyblog:
            from v11.models import PenaltyblogAdapter
            model_list += [PenaltyblogAdapter(kind) for kind in PenaltyblogAdapter.classes]
        fitted = []
        labels = ["home" if m.home_goals > m.away_goals else "away" if m.away_goals > m.home_goals else "draw" for m in calibration]
        for model in model_list:
            try:
                model.fit(history)
                cp = [model.predict(m.home, m.away).probabilities_1x2 for m in calibration]
                fitted.append((model, fit_temperature(cp, labels)))
            except (RuntimeError, ValueError) as exc:
                errors.append({"model": model.model_key, "fold": len(folds), "error_type": type(exc).__name__})
        for match in test:
            label = "home" if match.home_goals > match.away_goals else "away" if match.away_goals > match.home_goals else "draw"
            predictions = {}
            for model, t in fitted:
                try:
                    p = model.predict(match.home, match.away).probabilities_1x2
                    predictions[model.model_key] = p
                    predictions[model.model_key+"_calibrated"] = temperature(p, t)
                except ValueError as exc:
                    errors.append({"model": model.model_key, "match_id": match.match_id, "error_type": type(exc).__name__})
            # Quotes must be timestamped before the fold decision, and fresh then.
            quotes = [q for q in (archived_quotes or {}).get(match.match_id, [])
                      if q.market == "match_winner" and q.provider_updated_at is not None
                      and timedelta(0) <= decision_at-q.observed_at <= timedelta(minutes=30)
                      and timedelta(0) <= decision_at-q.provider_updated_at <= timedelta(minutes=30)]
            groups = defaultdict(list)
            for quote in quotes:
                groups[(quote.source, quote.bookmaker)].append(quote)
            for (source, book), group in sorted(groups.items()):
                if len(group) == 3 and {q.selection for q in group} == {"home", "draw", "away"}:
                    predictions[f"market:{source}:{book}"] = proportional_no_vig({q.selection: q.odds for q in group})
            observations.append({"match_id": match.match_id, "day": str(match.kickoff.date()), "label": label,
                                 "decision_at": decision_at.isoformat(), "predictions": predictions})
        folds.append({"decision_at": decision_at.isoformat(), "training_count": len(train),
                      "training_result_cutoff": max(m.result_observed_at for m in train).isoformat(),
                      "calibration_count": len(calibration), "test_ids": [m.match_id for m in test],
                      "temperatures": {model.model_key: t for model, t in fitted}})
        start = end
    metrics = {}
    for key in sorted({key for row in observations for key in row["predictions"]}):
        selected = [row for row in observations if key in row["predictions"]]
        p = [row["predictions"][key] for row in selected]
        y = [row["label"] for row in selected]
        loss = [(row["day"], multiclass_log_loss([row["predictions"][key]], [row["label"]])) for row in selected]
        metrics[key] = {"count": len(y), "brier": multiclass_brier(p, y), "log_loss": multiclass_log_loss(p, y),
                        "log_loss_day_bootstrap_95": grouped_interval(loss), "calibration": calibration_bins(p, y)}
    # Pairwise deltas use exactly the same matches, never mismatched populations.
    paired = []
    market_keys = [k for k in metrics if k.startswith("market:")]
    for model_key in (k for k in metrics if not k.startswith("market:")):
        for market_key in market_keys:
            common = [r for r in observations if model_key in r["predictions"] and market_key in r["predictions"]]
            deltas = [(r["day"], multiclass_log_loss([r["predictions"][model_key]], [r["label"]]) -
                       multiclass_log_loss([r["predictions"][market_key]], [r["label"]])) for r in common]
            paired.append({"model": model_key, "market": market_key, "count": len(deltas),
                           "log_loss_delta": sum(x for _, x in deltas)/len(deltas),
                           "day_bootstrap_95": grouped_interval(deltas)})
    return {"status": "research_only" if observations else "insufficient_data", "folds": folds,
            "prediction_count": len(observations), "metrics": metrics, "paired_market_comparisons": paired,
            "observations": observations, "errors": errors,
            "dataset_hash": digest({"matches": [m.model_dump(mode="json") for m in ordered]}),
            "roi": None, "clv": None,
            "limitations": ["ROI requires a prespecified selection policy and archived executable odds",
                            "CLV requires same-bookmaker closing quotes captured before kickoff",
                            "No strategy or model is promoted by this report"], "can_influence_picks": False}
