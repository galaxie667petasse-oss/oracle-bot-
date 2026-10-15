from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path

from v10.time import utc_now
from v11.contracts import Snapshot
from v11.evaluation import chronological_evaluation
from v11.ledger import Ledger
from v11.service import analyze


def main(argv=None):
    parser = argparse.ArgumentParser(description="Oracle V11, recherche pre-match sans mise ni publication")
    parser.add_argument("--ledger", default="variable/oracle-v11.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    imp = sub.add_parser("import-snapshot")
    imp.add_argument("file", type=Path)
    build = sub.add_parser("build-snapshot")
    build.add_argument("--odds-file", type=Path, required=True)
    build.add_argument("--results-file", type=Path, action="append", required=True)
    build.add_argument("--mapping", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--provenance", choices=["real_provider", "manual", "synthetic"], required=True)
    analysis = sub.add_parser("analyze")
    analysis.add_argument("--day", type=date.fromisoformat, required=True)
    analysis.add_argument("--penaltyblog", action="store_true")
    sub.add_parser("history")
    paper = sub.add_parser("paper-report")
    paper.add_argument("--model", required=True)
    paper.add_argument("--min-ev", type=float, default=.05)
    paper.add_argument("--closing-snapshot", type=Path)
    result = sub.add_parser("record-result")
    result.add_argument("--prediction-id", required=True)
    result.add_argument("--home", type=int, required=True)
    result.add_argument("--away", type=int, required=True)
    result.add_argument("--source", required=True)
    result.add_argument("--status", choices=["FT", "CANC", "PST", "AET"], default="FT")
    backup = sub.add_parser("backup")
    backup.add_argument("target", type=Path)
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("file", type=Path)
    evaluation.add_argument("--competition", required=True)
    evaluation.add_argument("--penaltyblog", action="store_true")
    collect = sub.add_parser("collect")
    collect.add_argument("--provider", choices=["api_football", "the_odds_api"], required=True)
    collect.add_argument("--day", type=date.fromisoformat)
    collect.add_argument("--sport")
    collect.add_argument("--allow-network", action="store_true")
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--cache-db", default="variable/v11-provider-cache.sqlite3", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build-snapshot":
            from v11.sources import build_snapshot
            mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
            snap = build_snapshot(json.loads(args.odds_file.read_text(encoding="utf-8")),
                                  [json.loads(p.read_text(encoding="utf-8")) for p in args.results_file],
                                  mapping["competitions"], mapping.get("teams"), args.provenance)
            if snap.captured_at > utc_now():
                raise ValueError("future source observation")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(snap.model_dump_json(indent=2))
            report = {"snapshot_id": Ledger(args.ledger).add_snapshot(snap.model_dump(mode="json")),
                      "history_count": len(snap.history), "provenance": snap.provenance}
        elif args.command == "evaluate":
            snap = Snapshot.model_validate_json(args.file.read_text(encoding="utf-8"))
            report = chronological_evaluation([m for m in snap.history if m.competition == args.competition],
                                              include_penaltyblog=args.penaltyblog)
            report["provenance"] = snap.provenance
        elif args.command == "collect":
            from v10.config import V10Settings
            from v10.db.migrations import upgrade_head
            from v10.db.session import create_engine_from_settings, create_session_factory, session_scope
            from v11.sources import Collector, coverage, football_fixtures, odds_snapshot
            if args.output.exists():
                raise ValueError("output must be a new file")
            # A separate migrated V10 cache database, never the historical DATABASE_URL.
            args.cache_db.parent.mkdir(parents=True, exist_ok=True)
            settings = V10Settings(DATABASE_URL="sqlite:///"+args.cache_db.resolve().as_posix())
            upgrade_head(settings)
            engine = create_engine_from_settings(settings)
            parameters = {"date": str(args.day)} if args.provider == "api_football" and args.day else {"sport": args.sport}
            now = utc_now()
            try:
                with session_scope(create_session_factory(engine)) as session:
                    collector = Collector(session, {"api_football": os.getenv("API_FOOTBALL_KEY", ""),
                                                     "the_odds_api": os.getenv("THE_ODDS_API_KEY", "")},
                                          allow_network=args.allow_network, max_calls=1)
                    try:
                        fetched = collector.fetch(args.provider, parameters, now)
                    except RuntimeError:
                        # Persist quota accounting even when a provider rejects a request.
                        session.commit()
                        raise
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with args.output.open("x", encoding="utf-8") as handle:
                    json.dump(fetched, handle, ensure_ascii=False, indent=2)
                if args.provider == "the_odds_api":
                    from v10.time import parse_utc
                    snapshot = odds_snapshot(fetched["payload"], parse_utc(fetched["fetched_at"]))
                    key = Ledger(args.ledger).add_snapshot(snapshot.model_dump(mode="json"))
                    report = {"snapshot_id": key, "coverage": coverage(snapshot), "cache_hit": fetched["cache_hit"]}
                else:
                    report = {"fixtures": football_fixtures(fetched["payload"]), "cache_hit": fetched["cache_hit"],
                              "cross_provider_join": "requires_explicit_verified_mapping"}
            finally:
                engine.dispose()
        else:
            ledger = Ledger(args.ledger)
            if args.command == "status":
                report = ledger.verify()
            elif args.command == "import-snapshot":
                snap = Snapshot.model_validate_json(args.file.read_text(encoding="utf-8"))
                if snap.captured_at > utc_now():
                    raise ValueError("future snapshot")
                report = {"snapshot_id": ledger.add_snapshot(snap.model_dump(mode="json")), "provenance": snap.provenance}
            elif args.command == "analyze":
                report = analyze(ledger, args.day, utc_now(), args.penaltyblog)
            elif args.command == "history":
                report = ledger.history()
            elif args.command == "paper-report":
                from v11.paper import paper_report
                closing = None
                if args.closing_snapshot:
                    closing_snapshot = Snapshot.model_validate_json(args.closing_snapshot.read_text(encoding="utf-8"))
                    records = ledger.history(500)
                    if any(r["provenance"] != closing_snapshot.provenance for r in records):
                        raise ValueError("closing provenance mismatch")
                    closing = {f.fixture_id: f.quotes for f in closing_snapshot.fixtures}
                report = paper_report(ledger.history(500), args.model, args.min_ev, closing)
                report["history_window_limit"] = 500
            elif args.command == "record-result":
                report = {"outcome_id": ledger.add_outcome(args.prediction_id, args.home, args.away, utc_now(), args.source, args.status)}
            else:
                report = ledger.backup(args.target)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        from v11.sources import SourceError
        # Do not print request URLs, headers, credentials or arbitrary provider bodies.
        print(json.dumps({"status": "blocked", "error_type": type(exc).__name__,
                          "reason": str(exc) if isinstance(exc, SourceError) else "invalid_input_or_local_configuration"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
