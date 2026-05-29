import tempfile
from pathlib import Path

import shadow_ledger
import shadow_simulator


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out1 = root / "reports" / "sim1.csv"
        out2 = root / "reports" / "sim2.csv"
        s1 = shadow_simulator.generate_simulated_ledger(str(out1), n=100, seed=42, edge_scenario="neutral")
        s2 = shadow_simulator.generate_simulated_ledger(str(out2), n=100, seed=42, edge_scenario="neutral")
        assert s1["rows"] == 100
        assert out1.read_text(encoding="utf-8") == out2.read_text(encoding="utf-8")
        rows = shadow_ledger.read_ledger(str(out1))
        assert len(rows) == 100
        assert all(float(row["taken_odds"]) > 1.01 for row in rows)
        assert all(row["result"] in {"win", "loss"} for row in rows)

        positive = shadow_simulator.generate_simulated_ledger(str(root / "reports" / "positive.csv"), n=200, seed=1, edge_scenario="positive_clv")
        negative = shadow_simulator.generate_simulated_ledger(str(root / "reports" / "negative.csv"), n=200, seed=1, edge_scenario="negative_clv")
        missing = shadow_simulator.generate_simulated_ledger(str(root / "reports" / "missing.csv"), n=90, seed=1, edge_scenario="missing_closing")
        assert positive["clv_mean"] > 0
        assert negative["clv_mean"] < 0
        assert missing["clv_rows"] < 90

        try:
            shadow_simulator.generate_simulated_ledger(str(root / "data" / "bad.csv"), n=10)
            raise AssertionError("ecriture data acceptee")
        except ValueError:
            pass

    print("test_shadow_simulator ok")


if __name__ == "__main__":
    main()
