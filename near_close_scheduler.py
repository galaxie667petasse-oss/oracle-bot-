import argparse
import html
import json
from pathlib import Path
from typing import Any, Dict, List

from shadow_ledger import read_ledger


DEFAULT_SPORT_MAP = {
    "J League": "soccer_japan_j_league",
    "Primera División - Chile": "soccer_chile_campeonato",
    "Primera Division - Chile": "soccer_chile_campeonato",
    "Super League - China": "soccer_china_superleague",
    "Allsvenskan - Sweden": "soccer_sweden_allsvenskan",
    "Eliteserien - Norway": "soccer_norway_eliteserien",
    "MLB": "baseball_mlb",
    "Veikkausliiga - Finland": "soccer_finland_veikkausliiga",
    "Brazil Serie B": "soccer_brazil_serie_b",
    "Brazil Série B": "soccer_brazil_serie_b",
    "Brazil SÃ©rie B": "soccer_brazil_serie_b",
    "Serie B - Brazil": "soccer_brazil_serie_b",
    "Spain Segunda": "soccer_spain_segunda_division",
    "Segunda Division - Spain": "soccer_spain_segunda_division",
    "Superettan - Sweden": "soccer_sweden_superettan",
}


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le planning near-close doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def load_sport_map(path: str = "") -> Dict[str, str]:
    merged = dict(DEFAULT_SPORT_MAP)
    for default_path in ("config/sport_key_map.example.json", "config/sport_key_map.local.json"):
        target = Path(default_path)
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged.update({str(k): str(v) for k, v in data.items()})
            except Exception:
                pass
    if path and Path(path).exists():
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            merged.update({str(k): str(v) for k, v in data.items()})
    return merged


def _pending_rows(ledger: str) -> List[Dict[str, Any]]:
    return [row for row in read_ledger(ledger) if not str(row.get("closing_odds") or "").strip()]


def build_schedule(ledger: str, sport_map_path: str = "", regions: str = "us,uk,eu", markets: str = "h2h") -> Dict[str, Any]:
    rows = _pending_rows(ledger)
    sport_map = load_sport_map(sport_map_path)
    by_league: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        by_league.setdefault(str(row.get("league") or "unknown"), []).append(row)
    schedule = []
    for league, league_rows in sorted(by_league.items()):
        sport_key = sport_map.get(league, "")
        warnings = []
        if not sport_key:
            warnings.append("sport_key absent: ajouter cette ligue dans config/sport_key_map.local.json")
        if league == "MLB":
            warnings.append("MLB hors football evidence")
        next_date = min([row.get("match_date") for row in league_rows if row.get("match_date")] or [""])
        suffix = sport_key or "mapping_manquant"
        near_file = f"reports/the_odds_api_{suffix}_near_close.csv"
        collect = (
            f"python the_odds_api_adapter.py --allow-network --sport {sport_key} --regions {regions} "
            f"--markets {markets} --near-close --output {near_file}"
            if sport_key else "mapping sport_key requis avant collecte"
        )
        schedule.append({
            "league": league,
            "sport_key": sport_key,
            "pending_count": len(league_rows),
            "next_match_date": next_date or None,
            "command_collect_near_close": collect,
            "command_dry_run": f"python near_close_workflow.py --ledger {ledger} --snapshots reports/odds_snapshots.csv --near-close-file {near_file} --dry-run" if sport_key else "mapping sport_key requis avant dry-run",
            "command_apply": f"python near_close_workflow.py --ledger {ledger} --snapshots reports/odds_snapshots.csv --near-close-file {near_file} --apply" if sport_key else "mapping sport_key requis avant apply",
            "mapping_recommendation": f'Ajouter "{league}": "SPORT_KEY" dans config/sport_key_map.local.json' if not sport_key else "",
            "warnings": warnings,
        })
    return {
        "ledger": ledger,
        "pending_total": len(rows),
        "leagues_count": len(schedule),
        "schedule": schedule,
        "lab_only": True,
        "can_influence_picks": False,
    }


def write_json(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_html(report: Dict[str, Any], output: str) -> Path:
    target = _safe_output(output)
    rows = "".join(
        f"<tr><td>{html.escape(str(item.get('league')))}</td><td>{html.escape(str(item.get('sport_key')))}</td><td>{item.get('pending_count')}</td><td>{html.escape(str(item.get('next_match_date')))}</td><td><code>{html.escape(str(item.get('command_collect_near_close')))}</code></td></tr>"
        for item in report.get("schedule") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body><h1>Near-Close Scheduler</h1>"
        f"<p>Pending total: {report.get('pending_total')}</p><table border='1'><tr><th>Ligue</th><th>Sport key</th><th>Pending</th><th>Date</th><th>Collecte</th></tr>"
        + rows
        + "</table><p>Commande reseau uniquement si l'utilisateur lance explicitement --allow-network.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any], commands_only: bool = False) -> None:
    print("Near-Close Scheduler Oracle")
    print(f"- Pending total: {report.get('pending_total')}")
    for item in report.get("schedule") or []:
        print(f"- {item.get('league')}: {item.get('pending_count')} observations, sport={item.get('sport_key') or 'mapping manquant'}")
        if commands_only:
            print(f"  collect: {item.get('command_collect_near_close')}")
            print(f"  dry-run: {item.get('command_dry_run')}")
            print(f"  apply: {item.get('command_apply')}")
        for warning in item.get("warnings") or []:
            print(f"  warning: {warning}")
    print("- Aucun reseau lance par ce scheduler.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Genere les commandes near-close par ligue.")
    parser.add_argument("--ledger", default="reports/shadow_ledger.csv")
    parser.add_argument("--sport-map", default="")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    parser.add_argument("--commands", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        report = build_schedule(args.ledger, args.sport_map)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report, commands_only=args.commands)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
