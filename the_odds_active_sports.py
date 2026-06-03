import argparse
import html
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from odds_source_config import get_api_key_from_env, load_odds_source_config


def _safe_output(path: str) -> Path:
    target = Path(path)
    if "data" in [part.lower() for part in target.parts]:
        raise ValueError("Le rapport active sports doit rester hors data/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def read_fixture(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fetch_active_sports(config: Dict[str, Any]) -> Any:
    source = config.get("the_odds_api") or {}
    key = get_api_key_from_env("the_odds_api", config)
    if not key:
        raise ValueError("Cle The Odds API absente dans l'environnement.")
    base_url = str(source.get("base_url") or "https://api.the-odds-api.com/v4").rstrip("/")
    query = urllib.parse.urlencode({"apiKey": key})
    request = urllib.request.Request(f"{base_url}/sports?{query}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_active_sports(payload: Any, group: str = "", include_inactive: bool = False) -> List[Dict[str, Any]]:
    items = payload if isinstance(payload, list) else payload.get("data") or payload.get("sports") or []
    wanted = str(group or "").strip().lower()
    rows: List[Dict[str, Any]] = []
    for item in items:
        row = {
            "key": str(item.get("key") or ""),
            "group": str(item.get("group") or ""),
            "title": str(item.get("title") or ""),
            "description": str(item.get("description") or ""),
            "active": bool(item.get("active", False)),
            "has_outrights": bool(item.get("has_outrights", False)),
        }
        if wanted and row["group"].lower() != wanted:
            continue
        if not include_inactive and not row["active"]:
            continue
        rows.append(row)
    return sorted(rows, key=lambda row: row["key"])


def build_report(payload: Any, group: str = "Soccer", include_inactive: bool = False) -> Dict[str, Any]:
    sports = normalize_active_sports(payload, group=group, include_inactive=include_inactive)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "group": group,
        "sports": sports,
        "active_count": len([row for row in sports if row.get("active")]),
        "sport_keys": [row["key"] for row in sports],
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
        "<tr>"
        f"<td>{html.escape(str(item.get('key')))}</td>"
        f"<td>{html.escape(str(item.get('title')))}</td>"
        f"<td>{html.escape(str(item.get('group')))}</td>"
        f"<td>{'oui' if item.get('active') else 'non'}</td>"
        f"<td>{'oui' if item.get('has_outrights') else 'non'}</td>"
        "</tr>"
        for item in report.get("sports") or []
    )
    target.write_text(
        "<!doctype html><html lang='fr'><meta charset='utf-8'><body>"
        "<h1>The Odds API - sports actifs</h1>"
        f"<p>Groupe: {html.escape(str(report.get('group')))} | actifs: {report.get('active_count')}</p>"
        "<table border='1'><tr><th>Key</th><th>Titre</th><th>Groupe</th><th>Actif</th><th>Outrights</th></tr>"
        + rows
        + "</table><p>Decouverte source uniquement, aucune mise.</p></body></html>",
        encoding="utf-8",
    )
    return target


def print_report(report: Dict[str, Any], dry_run: bool = False) -> None:
    print("The Odds API - active sports")
    print(f"- Groupe: {report.get('group')}")
    print(f"- Sports actifs: {report.get('active_count')}")
    if dry_run:
        print("- Dry-run: aucun reseau lance.")
    for key in report.get("sport_keys") or []:
        print(f"- {key}")
    print("- Les cles API ne sont jamais affichees.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Decouvre les sports actifs The Odds API, reseau desactive par defaut.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-network", action="store_true")
    parser.add_argument("--group", default="Soccer")
    parser.add_argument("--from-fixture", default="")
    parser.add_argument("--include-inactive", action="store_true")
    parser.add_argument("--output", default="")
    parser.add_argument("--html", default="")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.dry_run:
            report = build_report([], group=args.group, include_inactive=args.include_inactive)
            if args.output:
                write_json(report, args.output)
            if args.html:
                write_html(report, args.html)
            print_report(report, dry_run=True)
            return 0
        if args.from_fixture:
            payload = read_fixture(args.from_fixture)
        else:
            if not args.allow_network:
                raise ValueError("Reseau refuse par defaut. Utiliser --dry-run, --from-fixture ou --allow-network.")
            payload = fetch_active_sports(load_odds_source_config())
        report = build_report(payload, group=args.group, include_inactive=args.include_inactive)
        if args.output:
            write_json(report, args.output)
        if args.html:
            write_html(report, args.html)
        print_report(report)
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
