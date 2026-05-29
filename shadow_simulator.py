import argparse
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List

from shadow_ledger import LEDGER_COLUMNS, compute_clv, write_ledger


SCENARIOS = {"neutral", "positive_clv", "negative_clv", "lucky_roi", "unlucky_clv", "missing_closing"}


def ensure_output_path(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le simulateur shadow ne doit pas ecrire dans data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _result(rng: random.Random, probability: float) -> str:
    return "win" if rng.random() < probability else "loss"


def _closing_for_scenario(rng: random.Random, taken: float, scenario: str, idx: int) -> Any:
    if scenario == "missing_closing" and idx % 3 != 0:
        return ""
    if scenario in {"positive_clv", "unlucky_clv"}:
        factor = rng.uniform(0.965, 0.995)
    elif scenario in {"negative_clv", "lucky_roi"}:
        factor = rng.uniform(1.005, 1.045)
    else:
        factor = rng.uniform(0.99, 1.01)
    return round(max(1.02, taken * factor), 3)


def generate_simulated_ledger(output: str, n: int = 100, seed: int = 42, edge_scenario: str = "neutral") -> Dict[str, Any]:
    if edge_scenario not in SCENARIOS:
        raise ValueError("Scenario inconnu: " + edge_scenario)
    ensure_output_path(output)
    rng = random.Random(seed)
    rows: List[Dict[str, Any]] = []
    start = date(2026, 6, 1)
    for idx in range(n):
        taken = round(rng.uniform(1.55, 3.25), 3)
        closing = _closing_for_scenario(rng, taken, edge_scenario, idx)
        fair_prob = 1.0 / taken
        if edge_scenario == "lucky_roi":
            win_prob = min(0.88, fair_prob + 0.08)
        elif edge_scenario == "unlucky_clv":
            win_prob = max(0.08, fair_prob - 0.08)
        else:
            win_prob = min(0.88, max(0.08, fair_prob + rng.uniform(-0.03, 0.03)))
        result = _result(rng, win_prob)
        clv = compute_clv(taken, float(closing) if str(closing).strip() else None)
        rows.append({
            "shadow_id": f"sim_{seed}_{idx:05d}",
            "created_at": f"2026-05-30T00:{idx % 60:02d}:00",
            "match_date": str(start + timedelta(days=idx // 5)),
            "league": ["EPL", "La Liga", "Bundesliga", "Serie A", "Ligue 1"][idx % 5],
            "home_team": f"Home {idx % 20}",
            "away_team": f"Away {idx % 20}",
            "market_type": "h2h",
            "side": ["home", "away"][idx % 2],
            "taken_odds": taken,
            "bookmaker": "simulation",
            "signal_probability": round(min(0.95, max(0.05, win_prob)), 4),
            "market_probability": round(1.0 / taken, 4),
            "no_vig_probability": round(1.0 / taken, 4),
            "edge_probability": round(win_prob - 1.0 / taken, 4),
            "model_name": "simulation",
            "strategy_name": edge_scenario,
            "confidence_label": "simulation",
            "reason": "Simulation locale, aucune preuve reelle",
            "status": "settled",
            "result": result,
            "closing_odds": closing,
            "closing_source": "simulation" if str(closing).strip() else "",
            "clv_percent": clv["clv_percent"],
            "clv_available": clv["clv_available"],
            "notes": "Donnees synthetiques",
        })
    write_ledger(rows, output)
    clvs = [float(row["clv_percent"]) for row in rows if str(row.get("clv_available")) == "True"]
    return {
        "output": output,
        "rows": n,
        "seed": seed,
        "edge_scenario": edge_scenario,
        "clv_rows": len(clvs),
        "clv_mean": round(sum(clvs) / len(clvs), 6) if clvs else None,
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_summary(summary: Dict[str, Any]) -> None:
    print("Shadow Simulator Oracle Bot")
    print("- Simulation locale, aucune preuve reelle.")
    print(f"- Sortie: {summary.get('output')}")
    print(f"- Lignes: {summary.get('rows')}")
    print(f"- Scenario: {summary.get('edge_scenario')}")
    print(f"- CLV moyenne synthetique: {summary.get('clv_mean')}")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Genere un ledger shadow synthetique pour tester le workflow.")
    parser.add_argument("--output", default="reports/shadow_ledger_simulated.csv")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--edge-scenario", default="neutral", choices=sorted(SCENARIOS))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.n <= 0:
            raise ValueError("--n doit etre positif")
        summary = generate_simulated_ledger(args.output, args.n, args.seed, args.edge_scenario)
        print_summary(summary)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
