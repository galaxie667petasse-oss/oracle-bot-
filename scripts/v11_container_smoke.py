"""Run inside CI against the specifically named disposable test container."""
import argparse
import json
import subprocess
import time
import math
import random
from datetime import UTC, datetime, timedelta

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--container", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    assert args.container.startswith("oracle-v11-ci-"), "Only disposable CI containers are accepted"
    auth = {"Authorization": "Bearer ci-only-not-a-secret"}

    def wait_ready():
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            try:
                if httpx.get(args.url + "/health/live", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
        raise RuntimeError("container failed to start")

    wait_ready()
    uid = subprocess.check_output(["docker", "exec", args.container, "python", "-c", "import os; print(os.getuid())"], text=True).strip()
    assert uid != "0"
    now = datetime.now(UTC)
    rng = random.Random(11)

    def poisson(rate):
        product, count = 1.0, 0
        while product > math.exp(-rate):
            product *= rng.random()
            count += 1
        return count-1

    history = []
    for i in range(360):
        home, away = rng.sample(["A", "B", "C", "D", "E", "F"], 2)
        kickoff = now-timedelta(days=400-i)
        history.append({"match_id": f"synthetic:{i}", "competition": "ci", "home": home, "away": away,
                        "kickoff": kickoff.isoformat(), "result_observed_at": (kickoff+timedelta(hours=2)).isoformat(),
                        "home_goals": poisson(1.6), "away_goals": poisson(1.2)})
    quotes = [{"source": "synthetic", "bookmaker": "ci-test-book", "market": "match_winner", "selection": s,
               "odds": o, "observed_at": now.isoformat(), "provider_updated_at": now.isoformat()}
              for s, o in (("home", 2.2), ("draw", 3.4), ("away", 3.5))]
    snapshot = {"captured_at": now.isoformat(), "provenance": "synthetic", "fixtures": [{
        "fixture_id": "ci:fixture", "source": "synthetic", "competition": "ci", "home": "A", "away": "B",
        "kickoff": (now + timedelta(hours=6)).isoformat(), "observed_at": now.isoformat(), "quotes": quotes}], "history": history}
    with httpx.Client(base_url=args.url, timeout=30) as client:
        assert client.get("/api/v11/history").status_code == 401
        assert client.get("/metrics").status_code == 404
        assert client.post("/api/v11/snapshots", headers=auth, json=snapshot).status_code == 200
        response = client.post("/api/v11/analyze", headers=auth, params={"day": str(now.date())})
        assert response.status_code == 200
        before = client.get("/api/v11/history", headers=auth).json()
        # UTC midnight may move the fixture to tomorrow; use its actual UTC date.
        if not before:
            day = datetime.fromisoformat(snapshot["fixtures"][0]["kickoff"]).date()
            assert client.post("/api/v11/analyze", headers=auth, params={"day": str(day)}).status_code == 200
            before = client.get("/api/v11/history", headers=auth).json()
        assert len(before) == 1 and before[0]["decision"] == "ABSTAIN"
        assert len(before[0]["models"]) == 6 and not before[0]["model_errors"]
        assert len(before[0]["comparisons"]) == 18
    subprocess.run(["docker", "restart", args.container], check=True, capture_output=True)
    wait_ready()
    assert httpx.get(args.url + "/api/v11/history", headers=auth).json() == before
    backup = subprocess.check_output(["docker", "exec", args.container, "python", "-m", "v11", "backup",
                                      "variable/ci-restore.sqlite3"], text=True)
    verified = json.loads(backup)
    assert verified["hashes_ok"] and verified["counts"]["predictions"] == 1
    print(json.dumps({"status": "PASS", "non_root": True, "authentication": True, "models_executed": 6,
                      "restart_persistence": True, "backup_restoration": verified, "provenance": "synthetic"}))


if __name__ == "__main__":
    main()
