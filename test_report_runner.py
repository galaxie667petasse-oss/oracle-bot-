import os
import tempfile
from pathlib import Path

from dashboard_builder import build_dashboard
from report_runner import ReportCommand, command_set, run_report


def write_report(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        report_dir = root / "reports" / "oracle_test"
        db_path = root / "oracle_db.json"
        matches_path = root / "MATCHES.csv"
        db_path.write_text("{}", encoding="utf-8")
        matches_path.write_text("date,home,away\n", encoding="utf-8")
        before_db = db_path.read_text(encoding="utf-8")
        before_matches = matches_path.read_text(encoding="utf-8")
        os.environ["DB_FILE"] = str(db_path)

        manifest = run_report([
            ReportCommand("Succes", "success.txt", ["-c", "print('rapport ok')"], timeout=30),
            ReportCommand("Echec volontaire", "failure.txt", ["-c", "import sys; print('erreur test'); sys.exit(2)"], timeout=30),
            ReportCommand("Succes apres erreur", "success_2.txt", ["-c", "print('rapport ok 2')"], timeout=30),
        ], report_dir, Path.cwd())

        assert (root / "reports").exists()
        assert manifest["ok"] == 2
        assert manifest["failed"] == 1
        assert (report_dir / "success.txt").exists()
        assert (report_dir / "failure.txt").exists()
        assert (report_dir / "run_manifest.json").exists()
        assert db_path.read_text(encoding="utf-8") == before_db
        assert matches_path.read_text(encoding="utf-8") == before_matches

        write_report(report_dir / "pricing_report.txt", """
Rapport pricing Oracle Bot
- Records regles: 528066
- Marge moyenne H2H: 0.66% (marches=122915)
- Marge moyenne Over/Under: 1.83% (marches=79660)
- Marge faible (<= 3.00%): n=492342, ROI=-1.4%, profit=-7078.75
- Marge elevee (>= 8.00%): n=66, ROI=-16.3%, profit=-10.77
""")
        write_report(report_dir / "backtest_modern.txt", """
Backtest temporel Oracle Bot
- Records train: 408969 (2015-01-01 -> 2022-12-31)
- Records test: 66140 (2024-01-01 -> 2025-06-01)
Baseline marche brut
- ROI: -1.2%
Totals seulement
- ROI: -2.0%
Conclusion prudente
- Aucune regle jouable
""")
        write_report(report_dir / "favorite_report.txt", """
Rapport favoris H2H Oracle Bot
  - Tous favoris H2H [non confirme]
  - test n=1000, ROI=-2.5%
  - 1.60 <= cote < 1.80 [non confirme]
  - exterieur favori [fragile]
  - elo_diff fort positif [degradation recente]
""")
        write_report(report_dir / "stability_report.txt", "Rapport de stabilite annuelle\n- degradation recente\n- Aucun segment candidat coherent\n")
        write_report(report_dir / "ml_global.txt", """
Rapport ML leger Oracle Bot
- Test 2024+:
  - modele: n=66140, Brier=0.213805, log loss=0.615889
  - marche no-vig: Brier=0.2135, log loss=0.615094
- edge > 0.02: picks=2879, ROI=-5.06%, note=signal invalide
""")
        write_report(report_dir / "external_profile.txt", """
Score utilite Oracle:
  - odds: 5/5
  - xg: 0/5
  - leak_risk: eleve
  - verdict: utiliser comme enrichissement
""")

        summary = build_dashboard(report_dir)
        html = (report_dir / "index.html").read_text(encoding="utf-8")
        assert (report_dir / "summary.json").exists()
        assert "Backtest" in html
        assert "Pricing" in html
        assert "Favorite Report" in html
        assert "Stability" in html
        assert "ML" in html
        assert "External Dataset Lab" in html
        assert summary["records_count"] == 528066
        assert summary["pricing_low_margin_roi"] == -1.4
        assert summary["ml_global_brier_test"] == 0.213805
        assert any(command.name == "CLV analysis" for command in command_set("statistical"))
        assert any(command.name == "Benchmark governance" for command in command_set("full"))
        assert "CLV / Closing Line Value" in html
        assert "Validation statistique" in html
        assert "aucun pick automatique" in html.lower()

    print("test_report_runner ok")


if __name__ == "__main__":
    main()
