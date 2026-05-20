import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

from agents import agent_weights
from store import build_learning, save_db, load_db

REQUIRED_COLUMNS = ("date", "home", "away", "competition", "market_type", "pari", "odds", "result")


def _norm_result(value):
    value = str(value or "").strip().lower()
    if value in ("win", "won", "gagne", "gagné", "w"):
        return "win"
    if value in ("loss", "lost", "perdu", "lose", "l"):
        return "loss"
    raise ValueError(f"résultat invalide: {value!r}")


def _is_visible(row):
    value = str(row.get("visible") or row.get("type") or "").strip().lower()
    return value in ("1", "true", "yes", "oui", "visible", "pick", "picks")


def _decision(row, visible):
    value = str(row.get("decision") or "").strip().upper()
    if value in ("ACCEPTE", "SURVEILLANCE", "REFUSE"):
        return value
    return "SURVEILLANCE" if visible else "REFUSE"


def _pick_from_row(row, line_no):
    missing = [name for name in REQUIRED_COLUMNS if not str(row.get(name, "")).strip()]
    if missing:
        raise ValueError(f"ligne {line_no}: colonnes manquantes: {', '.join(missing)}")
    date_key = row["date"].strip()
    home = row["home"].strip()
    away = row["away"].strip()
    market_type = row["market_type"].strip()
    pari = row["pari"].strip()
    visible = _is_visible(row)
    pick = {
        "match_id": row.get("match_id") or f"backtest:{date_key}:{home}:{away}:{market_type}:{pari}",
        "date_key": date_key,
        "home": home,
        "away": away,
        "competition": row["competition"].strip(),
        "heure": row.get("heure", "historique") or "historique",
        "source": "backtest_csv",
        "bookmaker": row.get("bookmaker", "historique") or "historique",
        "pari": pari,
        "market_type": market_type,
        "odds": round(float(row["odds"]), 2),
        "result": _norm_result(row["result"]),
        "decision": _decision(row, visible),
        "shadow": not visible,
        "visible": visible,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    return pick


def import_csv(path):
    db = load_db()
    imported = skipped = 0
    with Path(path).open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("CSV vide ou sans en-têtes")
        missing = [name for name in REQUIRED_COLUMNS if name not in reader.fieldnames]
        if missing:
            raise ValueError(f"colonnes requises absentes: {', '.join(missing)}")
        for line_no, row in enumerate(reader, start=2):
            pick = _pick_from_row(row, line_no)
            scan = db.setdefault("scans", {}).setdefault(pick["date_key"], {
                "date_key": pick["date_key"],
                "date_label": pick["date_key"],
                "scanned_at": pick["imported_at"],
                "mode": "backtest",
                "version": "BACKTEST-CSV",
                "picks": [],
                "candidates": [],
                "rejected_count": 0,
            })
            scan.setdefault("picks", [])
            scan.setdefault("candidates", [])
            existing = {
                (p.get("match_id"), p.get("pari"), p.get("market_type"), p.get("date_key"))
                for p in (scan.get("picks", []) + scan.get("candidates", []))
            }
            key = (pick.get("match_id"), pick.get("pari"), pick.get("market_type"), pick.get("date_key"))
            if key in existing:
                skipped += 1
                continue
            if pick["visible"]:
                scan["picks"].append(pick)
            else:
                scan["candidates"].append(pick)
            scan["shadow_count"] = len(scan.get("candidates", []) or [])
            imported += 1
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)
    return imported, skipped, db["learning"].get("samples", 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Importe un historique CSV dans la mémoire Oracle Bot.")
    parser.add_argument("csv_path", help="Chemin du CSV backtest")
    args = parser.parse_args(argv)
    imported, skipped, samples = import_csv(args.csv_path)
    print(f"Import terminé: {imported} lignes ajoutées, {skipped} doublons ignorés, {samples} résultats appris.")


if __name__ == "__main__":
    main()
