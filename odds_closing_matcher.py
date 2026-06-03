import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from odds_normalizer import normalize_decimal_odds
from odds_snapshot_store import load_snapshots
from shadow_ledger import compute_clv, read_ledger, write_ledger
from team_name_normalizer import normalize_team_name


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _parse_dt(value: Any):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.fromisoformat(text[:19])
        except Exception:
            return None


def _minutes_before_kickoff(snapshot: Dict[str, Any]):
    captured = _parse_dt(snapshot.get("captured_at"))
    kickoff = _parse_dt(snapshot.get("kickoff_time"))
    if not captured or not kickoff:
        return None
    if captured.tzinfo is None and kickoff.tzinfo is not None:
        captured = captured.replace(tzinfo=kickoff.tzinfo)
    if kickoff.tzinfo is None and captured.tzinfo is not None:
        kickoff = kickoff.replace(tzinfo=captured.tzinfo)
    return (kickoff - captured).total_seconds() / 60.0


def _match_key(row: Dict[str, Any], same_bookmaker: bool = False) -> Tuple[str, ...]:
    league = str(row.get("league") or "")
    parts = [
        _norm(row.get("match_date")),
        _norm(league),
        normalize_team_name(row.get("home_team") or "", league=league).lower(),
        normalize_team_name(row.get("away_team") or "", league=league).lower(),
        _norm(row.get("market_type")),
        _norm(row.get("side")),
    ]
    if same_bookmaker:
        parts.append(_norm(row.get("bookmaker")))
    return tuple(parts)


def match_closing_snapshots(
    ledger_path: str,
    snapshots_path: str,
    event_id: str = "",
    league: str = "",
    match_date: str = "",
    bookmaker: str = "",
    same_bookmaker_only: bool = False,
    overwrite: bool = False,
    allow_ambiguous: bool = False,
    time_window_minutes: int = 0,
    prefer_latest_before_kickoff: bool = False,
    prefer_same_bookmaker: bool = False,
    only_shadow_pending: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    ledger_rows_all = read_ledger(ledger_path)
    ledger_rows = []
    for row in ledger_rows_all:
        if only_shadow_pending and str(row.get("closing_odds") or "").strip():
            continue
        if league and _norm(row.get("league")) != _norm(league):
            continue
        if match_date and _norm(row.get("match_date")) != _norm(match_date):
            continue
        if bookmaker and _norm(row.get("bookmaker")) != _norm(bookmaker):
            continue
        ledger_rows.append(row)
    snapshots = [
        row for row in load_snapshots(snapshots_path)
        if str(row.get("is_near_close") or "").lower() == "true"
        and row.get("validation_status") == "valid"
        and (not event_id or _norm(row.get("source_event_id")) == _norm(event_id))
        and (not league or _norm(row.get("league")) == _norm(league))
        and (not match_date or _norm(row.get("match_date")) == _norm(match_date))
        and (not bookmaker or _norm(row.get("bookmaker")) == _norm(bookmaker))
    ]
    grouped: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for row in snapshots:
        grouped.setdefault(_match_key(row, same_bookmaker_only), []).append(row)
    updated = 0
    matched = 0
    unmatched = 0
    ambiguous = 0
    skipped_existing = 0
    clv_added: List[float] = []
    errors: List[str] = []
    preview: List[Dict[str, Any]] = []
    unmatched_rows: List[Dict[str, Any]] = []
    ambiguous_rows: List[Dict[str, Any]] = []
    for row in ledger_rows:
        if str(row.get("closing_odds") or "").strip() and not overwrite:
            skipped_existing += 1
            continue
        key = _match_key(row, same_bookmaker_only)
        candidates = grouped.get(key) or []
        if time_window_minutes:
            filtered = []
            for candidate in candidates:
                minutes = _minutes_before_kickoff(candidate)
                if minutes is None or 0 <= minutes <= time_window_minutes:
                    filtered.append(candidate)
            candidates = filtered
        warning_different_bookmaker = False
        if prefer_same_bookmaker and candidates:
            same = [candidate for candidate in candidates if _norm(candidate.get("bookmaker")) == _norm(row.get("bookmaker"))]
            if same:
                candidates = same
            else:
                warning_different_bookmaker = True
        if not candidates:
            unmatched += 1
            unmatched_rows.append(row)
            continue
        if len(candidates) > 1 and prefer_latest_before_kickoff:
            before = [(candidate, _minutes_before_kickoff(candidate)) for candidate in candidates]
            before = [(candidate, minutes) for candidate, minutes in before if minutes is not None and minutes >= 0]
            if before:
                candidates = [sorted(before, key=lambda item: item[1])[0][0]]
        if len(candidates) > 1 and not allow_ambiguous:
            ambiguous += 1
            ambiguous_rows.append({"shadow_id": row.get("shadow_id"), "candidates": len(candidates), "match_date": row.get("match_date"), "home_team": row.get("home_team"), "away_team": row.get("away_team")})
            continue
        candidate = sorted(candidates, key=lambda item: item.get("snapshot_id") or "")[0]
        try:
            taken = normalize_decimal_odds(row.get("taken_odds"))
            closing = normalize_decimal_odds(candidate.get("odds"))
        except Exception as exc:
            errors.append(f"{row.get('shadow_id')}: {exc}")
            continue
        matched += 1
        change = {
            "shadow_id": row.get("shadow_id"),
            "closing_odds": closing,
            "closing_source": f"{candidate.get('source')}:{candidate.get('bookmaker')}",
            "snapshot_id": candidate.get("snapshot_id"),
            "clv_percent": compute_clv(taken, closing)["clv_percent"],
        }
        if warning_different_bookmaker:
            change["warning"] = "bookmaker different, aucun exact bookmaker match"
        preview.append(change)
        clv_added.append(float(change["clv_percent"]))
        if not dry_run:
            row["closing_odds"] = str(closing)
            row["closing_source"] = change["closing_source"] + ("; bookmaker different" if warning_different_bookmaker else "")
            row.update(compute_clv(taken, closing))
            updated += 1
    if not dry_run:
        if len(ledger_rows) != len(ledger_rows_all):
            # Les lignes filtrees sont les memes objets que dans ledger_rows_all.
            write_ledger(ledger_rows_all, ledger_path)
        else:
            write_ledger(ledger_rows, ledger_path)
    return {
        "ledger": ledger_path,
        "snapshots": snapshots_path,
        "shadow_rows": len(ledger_rows),
        "shadow_rows_total": len(ledger_rows_all),
        "near_close_snapshots": len(snapshots),
        "matches_found": matched,
        "matched": matched,
        "closing_updated": updated,
        "updated": updated,
        "skipped_existing": skipped_existing,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "clv_mean_added": round(sum(clv_added) / len(clv_added), 6) if clv_added else None,
        "errors": errors,
        "dry_run": dry_run,
        "only_shadow_pending": only_shadow_pending,
        "filters": {"event_id": event_id, "league": league, "match_date": match_date, "bookmaker": bookmaker},
        "preview": preview[:20],
        "unmatched_rows": unmatched_rows[:50],
        "ambiguous_rows": ambiguous_rows[:50],
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_dict_csv(rows: List[Dict[str, Any]], output: str) -> Path:
    target = Path(output)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Les sorties closing matcher doivent rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return target


def print_report(report: Dict[str, Any]) -> None:
    print("Matcher closing odds Oracle")
    print(f"- Lignes shadow lues: {report.get('shadow_rows')}")
    print(f"- Snapshots near-close: {report.get('near_close_snapshots')}")
    print(f"- Correspondances trouvees: {report.get('matches_found')}")
    print(f"- Closing mises a jour: {report.get('closing_updated')}")
    print(f"- Closing existantes ignorees: {report.get('skipped_existing')}")
    print(f"- Non matches: {report.get('unmatched')}")
    print(f"- Ambiguites: {report.get('ambiguous')}")
    print(f"- CLV moyenne ajoutee: {report.get('clv_mean_added')}")
    print("- Aucune cote closing n'est inventee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Associe des snapshots near-close au shadow ledger.")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--event-id", default="")
    parser.add_argument("--league", default="")
    parser.add_argument("--match-date", default="")
    parser.add_argument("--bookmaker", default="")
    parser.add_argument("--same-bookmaker-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-ambiguous", action="store_true")
    parser.add_argument("--time-window-minutes", type=int, default=0)
    parser.add_argument("--max-time-before-kickoff-minutes", type=int, default=0)
    parser.add_argument("--prefer-latest-before-kickoff", action="store_true")
    parser.add_argument("--prefer-same-bookmaker", action="store_true")
    parser.add_argument("--only-shadow-pending", action="store_true")
    parser.add_argument("--report", default="")
    parser.add_argument("--summary-json", default="")
    parser.add_argument("--unmatched-output", default="")
    parser.add_argument("--ambiguous-output", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = match_closing_snapshots(
            args.ledger,
            args.snapshots,
            event_id=args.event_id,
            league=args.league,
            match_date=args.match_date,
            bookmaker=args.bookmaker,
            same_bookmaker_only=args.same_bookmaker_only,
            overwrite=args.overwrite,
            allow_ambiguous=args.allow_ambiguous,
            time_window_minutes=args.max_time_before_kickoff_minutes or args.time_window_minutes,
            prefer_latest_before_kickoff=args.prefer_latest_before_kickoff,
            prefer_same_bookmaker=args.prefer_same_bookmaker,
            only_shadow_pending=args.only_shadow_pending,
            dry_run=args.dry_run,
        )
        print_report(report)
        output_path = args.summary_json or args.report
        if output_path:
            target = Path(output_path)
            if "data" in [part.lower() for part in target.parts]:
                raise ValueError("Le rapport closing matcher doit rester hors data/.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        if args.unmatched_output:
            print(f"- Non matches CSV: {write_dict_csv(report.get('unmatched_rows') or [], args.unmatched_output)}")
        if args.ambiguous_output:
            print(f"- Ambiguites CSV: {write_dict_csv(report.get('ambiguous_rows') or [], args.ambiguous_output)}")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
