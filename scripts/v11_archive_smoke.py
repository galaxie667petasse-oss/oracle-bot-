"""Read-only model smoke on a local archive. This is NOT a temporal backtest.

The V10 CSV loader reconstructs observed_at from event date. Those reconstructed
timestamps are explicitly rejected as evidence of real prematch availability.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v10.statistics.dataset import load_matches_csv
from v10.statistics.dixon_coles import DixonColesModel
from v10.statistics.elo import EloModel
from v10.statistics.poisson import PoissonModel
from v11.models import PenaltyblogAdapter


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args=parser.parse_args()
    original_hash=hashlib.file_digest(args.archive.open("rb"),"sha256").hexdigest()
    matches=load_matches_csv(str(args.archive),limit=500)
    if not matches:
        raise ValueError("no usable archive rows")
    competition=matches[0].competition
    history=[m for m in matches if m.competition==competition]
    target=history[-1]
    train=[m for m in history[:-1] if m.event_time<target.event_time]
    rows=[]
    for model in [PoissonModel(), DixonColesModel(), EloModel()]+[PenaltyblogAdapter(k) for k in PenaltyblogAdapter.classes]:
        try:
            pred=model.fit(train).predict(target.home_team,target.away_team)
            rows.append({"model":model.model_key,"status":"ok","probabilities":pred.probabilities_1x2})
        except (ValueError,RuntimeError) as exc:
            rows.append({"model":model.model_key,"status":"rejected","error_type":type(exc).__name__})
    assert original_hash==hashlib.file_digest(args.archive.open("rb"),"sha256").hexdigest()
    print(json.dumps({"archive_sha256":original_hash,"archive_unchanged":True,"loaded_rows":len(matches),
                      "competition":competition,"training_rows":len(train),"model_smokes":rows,
                      "real_archive":True,"temporal_validation_proven":False,
                      "blockers":["result availability timestamps absent","prematch quote timestamps absent"],
                      "roi":None,"clv":None,"can_influence_picks":False},indent=2))


if __name__=="__main__": main()
