import json
import tempfile
from pathlib import Path

import evidence_gate


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        empty = evidence_gate.build_evidence_gate()
        assert empty["global_status"] == "not_started"

        shadow = root / "reports" / "shadow.json"
        quality = root / "reports" / "quality.json"
        big5 = root / "reports" / "big5.json"
        clv = root / "reports" / "clv.json"
        write_json(shadow, {"signals_total": 25, "sample_size": 25, "clv_coverage": 0.0, "clv_mean": None, "roi": None, "verdict": "not_validated"})
        write_json(quality, {"verdict": "usable_with_warnings", "missing_closing": 25, "missing_results": 25})
        weak = evidence_gate.build_evidence_gate(str(shadow), str(quality))
        assert weak["global_status"] == "insufficient_evidence"
        assert any("sample shadow" in blocker for blocker in weak["blockers"])
        assert any("CLV absente" in blocker for blocker in weak["blockers"])

        write_json(shadow, {"signals_total": 300, "sample_size": 300, "clv_coverage": 90.0, "clv_mean": 0.01, "roi": 4.0, "verdict": "observation_only"})
        positive_small = evidence_gate.build_evidence_gate(str(shadow), str(quality))
        assert positive_small["global_status"] == "promising_but_unvalidated"

        write_json(quality, {"verdict": "invalid", "missing_closing": 0, "missing_results": 0})
        invalid = evidence_gate.build_evidence_gate(str(shadow), str(quality))
        assert invalid["global_status"] == "blocked"

        write_json(quality, {"verdict": "clean", "missing_closing": 0, "missing_results": 0})
        write_json(shadow, {"signals_total": 1000, "sample_size": 1000, "clv_coverage": 90.0, "clv_mean": 0.01, "roi": 4.0, "verdict": "deep_analysis_candidate"})
        deep = evidence_gate.build_evidence_gate(str(shadow), str(quality))
        assert deep["global_status"] == "ready_for_deep_review"

        write_json(big5, {"global": {"ready_for_big5_conclusion": True, "leagues_sample_ge_1000": 0, "leagues_clv_available": 0, "leagues_xg_improves_brier": 4}})
        write_json(clv, {"clv_calculable": False, "clv_calculable_now": False})
        big5_blocked = evidence_gate.build_evidence_gate(str(shadow), str(quality), str(big5), str(clv))
        assert any("Big5 sans CLV" in blocker for blocker in big5_blocked["blockers"])
        assert any("CLV readiness" in blocker for blocker in big5_blocked["blockers"])
        guard = root / "reports" / "guard.json"
        matchday = root / "reports" / "matchday_status.json"
        write_json(guard, {"verdict": "mixed_test_and_real", "near_close_without_taken_count": 1, "taken_without_near_close_count": 1})
        write_json(matchday, {"ready_for_dry_run": True, "taken": {"filled": 1}, "near_close": {"filled": 0}, "results": {"filled": 0}})
        guarded = evidence_gate.build_evidence_gate(str(shadow), str(quality), real_guard_path=str(guard), matchday_status_path=str(matchday))
        assert guarded["global_status"] == "blocked"
        assert any("guard reel" in blocker for blocker in guarded["blockers"])
        assert any("near-close sans taken" in blocker for blocker in guarded["blockers"])
        assert any("resultats manquants" in blocker for blocker in guarded["blockers"])

        write_json(guard, {"verdict": "needs_review", "phase": "pre_match", "near_close_without_taken_count": 0, "taken_without_near_close_count": 1})
        write_json(matchday, {"phase_detected": "pre_match_ready", "taken": {"valid_rows": 1}, "near_close": {"valid_rows": 0}, "results": {"valid_rows": 0}, "blockers": []})
        pre_match = evidence_gate.build_evidence_gate(str(shadow), str(quality), real_guard_path=str(guard), matchday_status_path=str(matchday))
        assert not any("matchday sans near-close" in blocker for blocker in pre_match["blockers"])
        assert any("Collecter la near-close" in step for step in pre_match["required_next_steps"])

        out_json = root / "reports" / "evidence_gate.json"
        out_html = root / "reports" / "evidence_gate.html"
        evidence_gate.write_json(big5_blocked, str(out_json))
        evidence_gate.write_html(big5_blocked, str(out_html))
        assert out_json.exists()
        assert out_html.exists()

    print("test_evidence_gate ok")


if __name__ == "__main__":
    main()
