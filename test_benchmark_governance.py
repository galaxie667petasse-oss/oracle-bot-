import json
import tempfile
from pathlib import Path

import benchmark_governance


def synthetic_db():
    records = []
    for idx, date in enumerate(["2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01", "2025-01-01"]):
        records.append({
            "id": f"r{idx}",
            "match_id": f"m{idx}",
            "date_key": date,
            "date": date,
            "home": "Alpha",
            "away": "Beta",
            "competition": "TEST",
            "market_type": "h2h",
            "pari": "Victoire Alpha",
            "odds": 1.8,
            "result": "win" if idx in (0, 1, 2, 4) else "loss",
            "shadow": True,
        })
        records.append({
            "id": f"t{idx}",
            "match_id": f"tm{idx}",
            "date_key": date,
            "date": date,
            "home": "Gamma",
            "away": "Delta",
            "competition": "TEST",
            "market_type": "total",
            "pari": "Plus de 2.5 buts",
            "odds": 1.9,
            "result": "loss" if idx in (3, 4) else "win",
            "shadow": True,
        })
    return {"scans": {"synthetic": {"picks": [], "candidates": records}}}


def main():
    validation_positive_test_negative = {
        "validation": {"picks": 500, "roi": 3.0},
        "test": {"picks": 500, "roi": -2.0},
    }
    assert benchmark_governance.robustness_score(validation_positive_test_negative) < 80

    failed = benchmark_governance._section("Echec volontaire", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    assert failed["ok"] is False
    assert "boom" in failed["error"]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        oracle_db = root / "oracle_db.json"
        oracle_db.write_text("{}", encoding="utf-8")
        before = oracle_db.read_text(encoding="utf-8")

        benchmark = benchmark_governance.build_benchmark(str(root / "features_absent.csv"), db=synthetic_db())
        assert benchmark["summary"]["sections_available"] >= 1
        assert benchmark["summary"]["sections_failed"]
        assert benchmark["registry"]
        assert oracle_db.read_text(encoding="utf-8") == before

        registry_path = root / "model_registry.json"
        benchmark_governance.write_registry(benchmark["registry"], str(registry_path))
        registry_text = registry_path.read_text(encoding="utf-8").lower()
        assert "secret" not in registry_text
        assert "token" not in registry_text
        assert "password" not in registry_text
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        assert isinstance(registry.get("models"), list)
        assert all("robustness_score" in entry for entry in registry["models"])

        summary_path = root / "reports" / "benchmark_summary.json"
        html_path = root / "reports" / "benchmark_governance.html"
        benchmark_governance.write_summary(benchmark, str(summary_path))
        benchmark_governance.write_html(benchmark, str(html_path))
        assert summary_path.exists()
        assert html_path.exists()
        assert "Gouvernance" in html_path.read_text(encoding="utf-8")

    print("test_benchmark_governance ok")


if __name__ == "__main__":
    main()
