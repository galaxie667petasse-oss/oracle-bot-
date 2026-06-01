import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from manual_odds_import import MANUAL_COLUMNS


RESULT_COLUMNS = ["shadow_id", "result", "notes"]


def _safe_dir(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le pack matchday doit rester hors data/.")
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read_source_matches(path: str, match_date: str) -> List[Dict[str, str]]:
    if not path:
        return []
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"CSV matchs introuvable: {path}")
    with source.open(newline="", encoding="utf-8-sig") as fh:
        rows = [dict(row) for row in csv.DictReader(fh)]
    out = []
    for row in rows:
        out.append({
            "captured_at": "",
            "source": "manual_csv",
            "league": row.get("league", ""),
            "match_date": row.get("match_date") or row.get("date") or match_date,
            "kickoff_time": row.get("kickoff_time", ""),
            "home_team": row.get("home_team") or row.get("home") or "",
            "away_team": row.get("away_team") or row.get("away") or "",
            "bookmaker": "",
            "market_type": row.get("market_type") or "h2h",
            "side": row.get("side") or "",
            "odds": "",
            "is_live": "false",
            "is_near_close": "false",
            "notes": "source manuelle reelle a verifier",
        })
    return out


def _write_csv(path: Path, columns: List[str], rows: List[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _checklist(match_date: str) -> str:
    return "\n".join([
        f"# Checklist matchday {match_date}",
        "",
        "## Matin",
        "- Preparer la liste de matchs.",
        "- Verifier que les fichiers test/demo sont archives si besoin.",
        "",
        "## Avant match",
        "- Noter les taken odds reelles avec captured_at.",
        "- Ne rien inventer si une cote manque.",
        "",
        "## 5-10 min avant kickoff",
        "- Noter les near-close reelles avec is_near_close=true.",
        "- Ne pas utiliser une near-close seule comme observation taken.",
        "",
        "## Apres match",
        "- Renseigner le resultat manuel.",
        "",
        "## Fin de journee",
        "- Lancer le rapport matchday.",
        "- Lire evidence gate.",
        "- Ne pas conclure avant sample significatif.",
    ])


def _readme(match_date: str) -> str:
    return "\n".join([
        f"# Matchday pack {match_date}",
        "",
        "Ce pack sert a collecter des observations shadow reelles.",
        "Il ne cree aucune mise et ne contacte aucun service externe.",
        "",
        "Fichiers:",
        "- matchday_manual_odds.csv : taken odds reelles.",
        "- matchday_near_close.csv : near-close reelles.",
        "- matchday_results.csv : resultats manuels.",
        "",
        "Toujours lancer un full-dry-run avant toute application.",
    ])


def create_pack(match_date: str, output_dir: str, from_csv: str = "") -> Dict[str, Any]:
    target = _safe_dir(output_dir)
    rows = _read_source_matches(from_csv, match_date)
    if not rows:
        rows = []
    near_rows = [dict(row, is_near_close="true", odds="", captured_at="") for row in rows]
    _write_csv(target / "matchday_manual_odds.csv", MANUAL_COLUMNS, rows)
    _write_csv(target / "matchday_near_close.csv", MANUAL_COLUMNS, near_rows)
    _write_csv(target / "matchday_results.csv", RESULT_COLUMNS, [])
    (target / "matchday_checklist.md").write_text(_checklist(match_date), encoding="utf-8")
    (target / "matchday_readme.md").write_text(_readme(match_date), encoding="utf-8")
    meta = {"date": match_date, "created_at": datetime.now().isoformat(timespec="seconds"), "from_csv": from_csv, "output_dir": str(target)}
    (target / "matchday_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "files": sorted(path.name for path in target.iterdir())}


def _count_filled(path: Path, key_columns: List[str]) -> Dict[str, Any]:
    if not path.exists():
        return {"exists": False, "rows": 0, "filled": 0}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        rows = [dict(row) for row in csv.DictReader(fh)]
    filled = sum(1 for row in rows if any(str(row.get(column) or "").strip() for column in key_columns))
    return {"exists": True, "rows": len(rows), "filled": filled}


def pack_status(pack_dir: str) -> Dict[str, Any]:
    target = Path(pack_dir)
    meta = {}
    if (target / "matchday_meta.json").exists():
        try:
            meta = json.loads((target / "matchday_meta.json").read_text(encoding="utf-8"))
        except Exception:
            meta = {}
    taken = _count_filled(target / "matchday_manual_odds.csv", ["odds", "captured_at"])
    near = _count_filled(target / "matchday_near_close.csv", ["odds", "captured_at"])
    results = _count_filled(target / "matchday_results.csv", ["shadow_id", "result"])
    warnings = []
    if taken["rows"] == 0:
        warnings.append("aucune ligne taken odds preparee")
    if near["rows"] == 0:
        warnings.append("aucune ligne near-close preparee")
    if taken["filled"] and not near["filled"]:
        warnings.append("taken odds presentes sans near-close renseignee")
    report = {
        "pack_dir": str(target),
        "date": meta.get("date"),
        "taken": taken,
        "near_close": near,
        "results": results,
        "warnings": warnings,
        "ready_for_dry_run": target.exists() and (target / "matchday_manual_odds.csv").exists(),
        "lab_only": True,
    }
    status_path = target / "matchday_status.json"
    if target.exists():
        status_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def print_report(title: str, report: Dict[str, Any]) -> None:
    print(title)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("- Observation seulement, aucune mise.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Prepare un pack de collecte matchday.")
    parser.add_argument("--date", default="")
    parser.add_argument("--from-csv", default="")
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--status", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.status:
            print_report("Status matchday pack Oracle", pack_status(args.status))
        else:
            if not args.date or not args.output_dir:
                raise ValueError("--date et --output-dir sont requis")
            print_report("Creation matchday pack Oracle", create_pack(args.date, args.output_dir, args.from_csv))
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
