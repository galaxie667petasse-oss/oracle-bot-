import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from odds_normalizer import normalize_decimal_odds
from odds_snapshot_store import load_snapshots
from shadow_ledger import compute_clv, read_ledger, write_ledger
from team_name_normalizer import normalize_team_name


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


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
    same_bookmaker_only: bool = False,
    overwrite: bool = False,
    allow_ambiguous: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    ledger_rows = read_ledger(ledger_path)
    snapshots = [
        row for row in load_snapshots(snapshots_path)
        if str(row.get("is_near_close") or "").lower() == "true" and row.get("validation_status") == "valid"
    ]
    grouped: Dict[Tuple[str, ...], List[Dict[str, Any]]] = {}
    for row in snapshots:
        grouped.setdefault(_match_key(row, same_bookmaker_only), []).append(row)
    updated = 0
    matched = 0
    unmatched = 0
    ambiguous = 0
    errors: List[str] = []
    preview: List[Dict[str, Any]] = []
    for row in ledger_rows:
        if str(row.get("closing_odds") or "").strip() and not overwrite:
            continue
        key = _match_key(row, same_bookmaker_only)
        candidates = grouped.get(key) or []
        if not candidates:
            unmatched += 1
            continue
        if len(candidates) > 1 and not allow_ambiguous:
            ambiguous += 1
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
        preview.append(change)
        if not dry_run:
            row["closing_odds"] = str(closing)
            row["closing_source"] = change["closing_source"]
            row.update(compute_clv(taken, closing))
            updated += 1
    if not dry_run:
        write_ledger(ledger_rows, ledger_path)
    return {
        "ledger": ledger_path,
        "snapshots": snapshots_path,
        "shadow_rows": len(ledger_rows),
        "near_close_snapshots": len(snapshots),
        "matches_found": matched,
        "closing_updated": updated,
        "unmatched": unmatched,
        "ambiguous": ambiguous,
        "errors": errors,
        "dry_run": dry_run,
        "preview": preview[:20],
        "lab_only": True,
        "can_influence_picks": False,
    }


def print_report(report: Dict[str, Any]) -> None:
    print("Matcher closing odds Oracle")
    print(f"- Lignes shadow lues: {report.get('shadow_rows')}")
    print(f"- Snapshots near-close: {report.get('near_close_snapshots')}")
    print(f"- Correspondances trouvees: {report.get('matches_found')}")
    print(f"- Closing mises a jour: {report.get('closing_updated')}")
    print(f"- Non matches: {report.get('unmatched')}")
    print(f"- Ambiguites: {report.get('ambiguous')}")
    print("- Aucune cote closing n'est inventee.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Associe des snapshots near-close au shadow ledger.")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--snapshots", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--same-bookmaker-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--allow-ambiguous", action="store_true")
    parser.add_argument("--report", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = match_closing_snapshots(
            args.ledger,
            args.snapshots,
            same_bookmaker_only=args.same_bookmaker_only,
            overwrite=args.overwrite,
            allow_ambiguous=args.allow_ambiguous,
            dry_run=args.dry_run,
        )
        print_report(report)
        if args.report:
            target = Path(args.report)
            if "data" in [part.lower() for part in target.parts]:
                raise ValueError("Le rapport closing matcher doit rester hors data/.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
