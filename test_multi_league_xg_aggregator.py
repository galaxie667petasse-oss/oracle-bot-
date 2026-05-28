import json
import tempfile
from pathlib import Path

import multi_league_xg_aggregator as aggregator


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def model_payload(roi, picks, clv=False, promotion=False, improves_brier=True, improves_log=True):
    return {
        "market_baseline": {"test": {"brier": 0.21, "log_loss": 0.61}},
        "comparison": {
            "market": {"brier": 0.21, "log_loss": 0.61},
            "with_xg": {"brier": 0.20 if improves_brier else 0.22, "log_loss": 0.60 if improves_log else 0.62},
            "delta_brier_xg_vs_market": -0.01 if improves_brier else 0.01,
            "delta_log_loss_xg_vs_market": -0.01 if improves_log else 0.01,
        },
        "verdict": {
            "xg_improves_brier": improves_brier,
            "xg_improves_log_loss": improves_log,
            "edge_test_positive": roi > 0,
            "sample_test_sufficient": picks >= 1000,
            "clv_available": clv,
            "promotion_allowed": promotion,
            "selected_test": {"roi": roi, "picks": picks},
            "rejection_reasons": [] if promotion else ["CLV absente"] if not clv else [],
        },
    }


def quality_payload(verdict="exploitable_rolling_xg"):
    return {"verdict": verdict, "rows": 1900, "xg_coverage": 100.0, "lab_only": True, "can_influence_picks": False}


def join_payload(rate=98.0, quality="excellent"):
    return {
        "join_rate_after_alias": rate,
        "join_quality": quality,
        "modeling_allowed_by_join_quality": quality != "insuffisant",
        "lab_only": True,
        "can_influence_picks": False,
    }


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        reports = root / "reports"

        empty = aggregator.build_summary(str(reports))
        assert empty["global"]["leagues_available"] == 0
        assert empty["global"]["robust_candidates"] == 0

        write_json(reports / "understat_epl_2020_2025_quality.json", quality_payload())
        write_json(reports / "understat_epl_2020_2025_join_diagnostics.json", join_payload())
        write_json(reports / "understat_epl_2020_2025_xg_model.json", model_payload(roi=-0.1, picks=1200, clv=False))
        one = aggregator.build_summary(str(reports))
        epl = next(item for item in one["leagues"] if item["league"] == "EPL")
        assert one["global"]["leagues_available"] == 1
        assert epl["status"] == "observation technique"
        assert epl["promotion_allowed"] is False

        write_json(reports / "laliga_2020_2025_quality.json", quality_payload())
        write_json(reports / "laliga_2020_2025_join_diagnostics.json", join_payload(99.89, "excellent"))
        write_json(reports / "laliga_2020_2025_xg_model.json", model_payload(roi=1.84, picks=440, clv=False))
        multi = aggregator.build_summary(str(reports))
        laliga = next(item for item in multi["leagues"] if item["league"] == "LaLiga")
        assert laliga["status"] == "watchlist maximum"
        assert "CLV absente" in laliga["rejection_reasons"]
        assert "sample edge test inferieur a 1000" in laliga["rejection_reasons"]
        assert multi["global"]["robust_candidates"] == 0

        write_json(reports / "bundesliga_2020_2025_quality.json", quality_payload())
        write_json(reports / "bundesliga_2020_2025_join_diagnostics.json", join_payload(39.89, "insuffisant"))
        write_json(reports / "bundesliga_2020_2025_xg_model.json", model_payload(roi=3.0, picks=1200, clv=True, promotion=True))
        blocked = aggregator.build_summary(str(reports))
        bundes = next(item for item in blocked["leagues"] if item["league"] == "Bundesliga")
        assert bundes["status"] == "rejet"
        assert bundes["promotion_allowed"] is False
        assert "jointure externe insuffisante" in bundes["rejection_reasons"]

        out_json = reports / "big5_xg_summary.json"
        out_html = reports / "big5_xg_summary.html"
        aggregator.write_json(blocked, str(out_json))
        aggregator.write_html(blocked, str(out_html))
        assert out_json.exists()
        assert out_html.exists()
        assert "Big 5 xG Lab Summary" in out_html.read_text(encoding="utf-8")

    print("test_multi_league_xg_aggregator ok")


if __name__ == "__main__":
    main()
