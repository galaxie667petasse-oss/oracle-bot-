import argparse
import csv
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from pricing import (
    expected_value,
    fair_odds,
    implied_probability,
    market_margin,
    remove_vig_1x2,
    remove_vig_two_way,
)
from recency import PERIOD_LABELS, PERIOD_ORDER, data_weight_for_period, period_bucket


SCORE_HOME_COLUMNS = ("FTHome", "FTHG")
SCORE_AWAY_COLUMNS = ("FTAway", "FTAG")
DATE_COLUMNS = ("MatchDate", "Date")
REQUIRED_MATCH_COLUMNS = ("Division", "HomeTeam", "AwayTeam")
OVER25_COLUMNS = ("MaxOver25", "Max>2.5", "AvgOver25", "Avg>2.5", "OddOver25", "Over25", "O25", "B365>2.5", "P>2.5")
UNDER25_COLUMNS = ("MaxUnder25", "Max<2.5", "AvgUnder25", "Avg<2.5", "OddUnder25", "Under25", "U25", "B365<2.5", "P<2.5")
BTTS_YES_COLUMNS = ("MaxBTTSYes", "AvgBTTSYes", "B365BTTSYes", "BTTSYes")
BTTS_NO_COLUMNS = ("MaxBTTSNo", "AvgBTTSNo", "B365BTTSNo", "BTTSNo")


@dataclass
class ImportStats:
    matches_lus: int = 0
    matches_ignores: int = 0
    candidats_crees: int = 0
    candidats_csv: int = 0
    nouveaux_importes: int = 0
    deja_presents_ignores: int = 0
    h2h_crees: int = 0
    draw_crees: int = 0
    over_crees: int = 0
    under_crees: int = 0
    over_under_crees: int = 0
    btts_crees: int = 0
    doublons_ignores: int = 0
    total_appris: int = 0
    date_min_importee: str = ""
    date_max_importee: str = ""
    distribution_annuelle: Dict[str, int] = None
    distribution_periode: Dict[str, int] = None
    periode_dominante: str = ""
    poids_agents: Dict[str, float] = None

    def __post_init__(self):
        if self.poids_agents is None:
            self.poids_agents = {}
        if self.distribution_annuelle is None:
            self.distribution_annuelle = {}
        if self.distribution_periode is None:
            self.distribution_periode = {}


def _value(row: Dict[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def parse_float(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text or text.lower() in {"nan", "na", "n/a", "null", "none"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not math.isfinite(number) or number <= 1.01:
        return None
    return number


def parse_number(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if text == "":
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_date(value: str) -> Optional[str]:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return None


def in_date_range(date_key: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
    if date_from and date_key < date_from:
        return False
    if date_to and date_key > date_to:
        return False
    return True


def odds_from_columns(row: Dict[str, Any], *columns: str) -> Tuple[Optional[float], str]:
    for column in columns:
        odds = parse_float(row.get(column))
        if odds is not None:
            return odds, column
    return None, ""


def best_odds(row: Dict[str, Any]) -> Dict[str, Tuple[Optional[float], str]]:
    return {
        "h2h_home": odds_from_columns(row, "MaxHome", "OddHome"),
        "draw": odds_from_columns(row, "MaxDraw", "OddDraw"),
        "h2h_away": odds_from_columns(row, "MaxAway", "OddAway"),
        "over25": odds_from_columns(row, "MaxOver25", "Over25", *[c for c in OVER25_COLUMNS if c not in ("MaxOver25", "Over25")]),
        "under25": odds_from_columns(row, "MaxUnder25", "Under25", *[c for c in UNDER25_COLUMNS if c not in ("MaxUnder25", "Under25")]),
        "btts_yes": odds_from_columns(row, *BTTS_YES_COLUMNS),
        "btts_no": odds_from_columns(row, *BTTS_NO_COLUMNS),
    }


def _rounded(value: Any, digits: int = 6) -> Optional[float]:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _pricing_fields(price: float, no_vig_probability: Optional[float] = None, margin: Optional[float] = None) -> Dict[str, float]:
    fields: Dict[str, float] = {}
    implied = _rounded(implied_probability(price))
    if implied is not None:
        fields["implied_probability"] = implied
    if no_vig_probability is None or margin is None:
        return fields
    no_vig = _rounded(no_vig_probability)
    fair = _rounded(fair_odds(no_vig_probability), digits=4)
    ev = _rounded(expected_value(no_vig_probability, price))
    margin_value = _rounded(margin)
    if no_vig is not None:
        fields["no_vig_probability"] = no_vig
    if margin_value is not None:
        fields["market_margin"] = margin_value
    if fair is not None:
        fields["fair_odds_market"] = fair
    if ev is not None:
        fields["ev_market_baseline"] = ev
    return fields


def pricing_context(odds: Dict[str, Tuple[Optional[float], str]]) -> Dict[str, Dict[str, float]]:
    context: Dict[str, Dict[str, float]] = {}

    h2h_prices = {key: odds[key][0] for key in ("h2h_home", "draw", "h2h_away")}
    h2h_probabilities = [implied_probability(price) for price in h2h_prices.values()]
    h2h_margin = market_margin(h2h_probabilities) if all(p is not None for p in h2h_probabilities) else None
    h2h_no_vig = remove_vig_1x2(h2h_prices["h2h_home"], h2h_prices["draw"], h2h_prices["h2h_away"])
    if h2h_no_vig is not None and h2h_margin is not None:
        context["h2h_home"] = _pricing_fields(float(h2h_prices["h2h_home"]), h2h_no_vig["home"], h2h_margin)
        context["draw"] = _pricing_fields(float(h2h_prices["draw"]), h2h_no_vig["draw"], h2h_margin)
        context["h2h_away"] = _pricing_fields(float(h2h_prices["h2h_away"]), h2h_no_vig["away"], h2h_margin)

    total_prices = {key: odds[key][0] for key in ("over25", "under25")}
    total_probabilities = [implied_probability(price) for price in total_prices.values()]
    total_margin = market_margin(total_probabilities) if all(p is not None for p in total_probabilities) else None
    total_no_vig = remove_vig_two_way(total_prices["over25"], total_prices["under25"])
    if total_no_vig is not None and total_margin is not None:
        context["over25"] = _pricing_fields(float(total_prices["over25"]), total_no_vig["over"], total_margin)
        context["under25"] = _pricing_fields(float(total_prices["under25"]), total_no_vig["under"], total_margin)

    return context


def has_h2h_odds(row: Dict[str, Any]) -> bool:
    odds = best_odds(row)
    return all(odds[key][0] is not None for key in ("h2h_home", "draw", "h2h_away"))


def has_over_under_odds(row: Dict[str, Any]) -> bool:
    odds = best_odds(row)
    return odds["over25"][0] is not None and odds["under25"][0] is not None


def has_btts_odds(row: Dict[str, Any]) -> bool:
    odds = best_odds(row)
    return odds["btts_yes"][0] is not None and odds["btts_no"][0] is not None


def result_for_market(home_goals: int, away_goals: int, market_key: str) -> str:
    total = home_goals + away_goals
    won = {
        "h2h_home": home_goals > away_goals,
        "draw": home_goals == away_goals,
        "h2h_away": away_goals > home_goals,
        "over25": total >= 3,
        "under25": total <= 2,
        "btts_yes": home_goals > 0 and away_goals > 0,
        "btts_no": home_goals == 0 or away_goals == 0,
    }.get(market_key, False)
    return "win" if won else "loss"


def _optional_float(row: Dict[str, Any], column: str):
    value = parse_number(row.get(column))
    return value if value is not None else ""


def xgabora_features(row: Dict[str, Any]) -> Dict[str, Any]:
    home_elo = _optional_float(row, "HomeElo")
    away_elo = _optional_float(row, "AwayElo")
    features = {
        "home_elo": home_elo,
        "away_elo": away_elo,
        "form3_home": _optional_float(row, "Form3Home"),
        "form3_away": _optional_float(row, "Form3Away"),
        "form5_home": _optional_float(row, "Form5Home"),
        "form5_away": _optional_float(row, "Form5Away"),
    }
    if home_elo != "" and away_elo != "":
        features["elo_diff"] = round(float(home_elo) - float(away_elo), 2)
    else:
        features["elo_diff"] = ""
    return {key: value for key, value in features.items() if value != ""}


def _training_votes(market_type: str, odds: float, features: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    elo_diff = float(features.get("elo_diff", 0) or 0)
    market_score = 1 if 1.45 <= odds <= 2.60 else -1 if odds >= 4.0 else 0
    risk_score = -2 if odds >= 3.8 else -1 if odds >= 3.1 else 1
    rhythm_score = 1 if market_type in ("total", "btts") else 0
    value_score = 0
    if market_type == "h2h" and abs(elo_diff) >= 80 and odds >= 1.7:
        value_score = 1
    return {
        "marche": {"vote": "ACCEPTE" if market_score > 0 else "REFUSE" if market_score < 0 else "SURVEILLANCE", "score": market_score, "note": "cote historique réelle"},
        "valeur": {"vote": "ACCEPTE" if value_score > 0 else "SURVEILLANCE", "score": value_score, "note": "signal Elo disponible" if value_score else "pas de value calculée"},
        "risque": {"vote": "ACCEPTE" if risk_score > 0 else "REFUSE" if risk_score < 0 else "SURVEILLANCE", "score": risk_score, "note": "risque estimé par niveau de cote"},
        "rythme": {"vote": "ACCEPTE" if rhythm_score > 0 else "SURVEILLANCE", "score": rhythm_score, "note": "marché buts" if market_type in ("total", "btts") else "rythme non modélisé"},
        "memoire": {"vote": "SURVEILLANCE", "score": 0, "note": "échantillon import xgabora"},
        "contradiction": {"vote": "REFUSE" if odds >= 4.0 else "SURVEILLANCE", "score": -1 if odds >= 4.0 else 0, "note": "cote très haute" if odds >= 4.0 else "pas d'alerte majeure"},
    }


def row_to_candidates(row: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], str]:
    date_key = parse_date(_value(row, *DATE_COLUMNS))
    home = _value(row, "HomeTeam")
    away = _value(row, "AwayTeam")
    competition = _value(row, "Division") or "UNKNOWN"
    home_goals = parse_int(_value(row, *SCORE_HOME_COLUMNS))
    away_goals = parse_int(_value(row, *SCORE_AWAY_COLUMNS))
    if not date_key or not home or not away or home_goals is None or away_goals is None:
        return "", [], "score_final_manquant"

    odds = best_odds(row)
    price_context = pricing_context(odds)
    features = xgabora_features(row)
    bucket = period_bucket(date_key)
    weight = data_weight_for_period(bucket)
    specs = [
        ("h2h_home", "h2h", f"Victoire {home}", "home"),
        ("draw", "draw", "Match nul", "draw"),
        ("h2h_away", "h2h", f"Victoire {away}", "away"),
        ("over25", "total", "Plus de 2.5 buts", "over_under"),
        ("under25", "total", "Moins de 2.5 buts", "over_under"),
        ("btts_yes", "btts", "Les deux équipes marquent - Oui", "btts"),
        ("btts_no", "btts", "Les deux équipes marquent - Non", "btts"),
    ]
    candidates = []
    for market_key, market_type, pari, family in specs:
        price, source_column = odds[market_key]
        if price is None:
            continue
        price_fields = price_context.get(market_key) or _pricing_fields(float(price))
        votes = _training_votes(market_type, float(price), features)
        agent_accepts = sum(1 for v in votes.values() if v.get("vote") == "ACCEPTE")
        agent_rejects = sum(1 for v in votes.values() if v.get("vote") == "REFUSE")
        council_score = round(sum(float(v.get("score", 0) or 0) for v in votes.values()), 2)
        candidate = {
            "match_id": f"xgabora:{date_key}:{home}:{away}",
            "date_key": date_key,
            "home": home,
            "away": away,
            "competition": competition,
            "heure": _value(row, "MatchTime") or "historique",
            "source": "xgabora_matches_csv",
            "bookmaker": source_column,
            "odds_source_column": source_column,
            "pari": pari,
            "market_type": market_type,
            "odds": round(float(price), 2),
            "result": result_for_market(home_goals, away_goals, market_key),
            "score": f"{home_goals}-{away_goals}",
            "decision": "SURVEILLANCE",
            "shadow": True,
            "visible": False,
            "import_family": family,
            "period_bucket": bucket,
            "data_weight": weight,
            "agent_votes": votes,
            "agent_accepts": agent_accepts,
            "agent_rejects": agent_rejects,
            "council_score": council_score,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            **price_fields,
            **features,
        }
        candidates.append(candidate)
    if not candidates:
        return date_key, [], "cotes_manquantes"
    return date_key, candidates, ""


def _candidate_key(candidate: Dict[str, Any]) -> tuple:
    try:
        odds = round(float(candidate.get("odds", 0) or 0), 4)
    except Exception:
        odds = 0
    return (
        candidate.get("date_key"),
        candidate.get("home"),
        candidate.get("away"),
        candidate.get("market_type"),
        candidate.get("pari"),
        odds,
    )


def _mark_imported_match(stats: ImportStats, date_key: str) -> None:
    if not date_key:
        return
    stats.date_min_importee = min(stats.date_min_importee, date_key) if stats.date_min_importee else date_key
    stats.date_max_importee = max(stats.date_max_importee, date_key) if stats.date_max_importee else date_key
    year = date_key[:4]
    stats.distribution_annuelle[year] = stats.distribution_annuelle.get(year, 0) + 1
    bucket = period_bucket(date_key)
    stats.distribution_periode[bucket] = stats.distribution_periode.get(bucket, 0) + 1
    stats.periode_dominante = max(stats.distribution_periode.items(), key=lambda item: item[1])[0]


def load_candidates(csv_path: str, limit: Optional[int] = None, date_from: Optional[str] = None, date_to: Optional[str] = None, competitions: Optional[Iterable[str]] = None) -> Tuple[List[Dict[str, Any]], ImportStats]:
    stats = ImportStats()
    candidates = []
    seen = set()
    eligible_seen = 0
    wanted_competitions = {c.strip() for c in competitions or [] if c.strip()}
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            competition = _value(row, "Division")
            if wanted_competitions and competition not in wanted_competitions:
                stats.matches_ignores += 1
                continue
            raw_date_key = parse_date(_value(row, *DATE_COLUMNS))
            if raw_date_key and not in_date_range(raw_date_key, date_from, date_to):
                continue
            if not raw_date_key and (date_from or date_to):
                stats.matches_ignores += 1
                continue
            if limit is not None and eligible_seen >= limit:
                break
            eligible_seen += 1
            stats.matches_lus += 1
            date_key, row_candidates, reason = row_to_candidates(row)
            if date_key and not in_date_range(date_key, date_from, date_to):
                stats.matches_ignores += 1
                continue
            if not row_candidates:
                stats.matches_ignores += 1
                continue
            added_for_match = 0
            for candidate in row_candidates:
                key = _candidate_key(candidate)
                if key in seen:
                    stats.doublons_ignores += 1
                    continue
                seen.add(key)
                candidates.append(candidate)
                added_for_match += 1
                stats.candidats_crees += 1
                family = candidate.get("import_family")
                if family in ("home", "away"):
                    stats.h2h_crees += 1
                elif family == "draw":
                    stats.draw_crees += 1
                elif family == "over_under":
                    stats.over_under_crees += 1
                    if candidate.get("pari") == "Plus de 2.5 buts":
                        stats.over_crees += 1
                    elif candidate.get("pari") == "Moins de 2.5 buts":
                        stats.under_crees += 1
                elif family == "btts":
                    stats.btts_crees += 1
            if added_for_match == 0:
                stats.matches_ignores += 1
            else:
                _mark_imported_match(stats, date_key)
    return candidates, stats


def import_candidates(candidates: List[Dict[str, Any]], dry_run: bool = False) -> ImportStats:
    stats = ImportStats(candidats_crees=len(candidates), candidats_csv=len(candidates))
    stats.h2h_crees = sum(1 for c in candidates if c.get("import_family") in ("home", "away"))
    stats.draw_crees = sum(1 for c in candidates if c.get("import_family") == "draw")
    stats.over_crees = sum(1 for c in candidates if c.get("import_family") == "over_under" and c.get("pari") == "Plus de 2.5 buts")
    stats.under_crees = sum(1 for c in candidates if c.get("import_family") == "over_under" and c.get("pari") == "Moins de 2.5 buts")
    stats.over_under_crees = sum(1 for c in candidates if c.get("import_family") == "over_under")
    stats.btts_crees = sum(1 for c in candidates if c.get("import_family") == "btts")
    if dry_run:
        return stats

    from agents import agent_weights
    from store import build_learning, load_db, save_db, scan_records

    db = load_db()
    existing_keys = {
        _candidate_key(p)
        for scan in db.get("scans", {}).values()
        for p in scan_records(scan)
    }
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in existing_keys:
            stats.deja_presents_ignores += 1
            stats.doublons_ignores += 1
            continue
        date_key = candidate["date_key"]
        scan = db.setdefault("scans", {}).setdefault(date_key, {
            "date_key": date_key,
            "date_label": date_key,
            "scanned_at": candidate.get("imported_at"),
            "mode": "xgabora_import",
            "version": "XGABORA-HISTORICAL",
            "picks": [],
            "candidates": [],
            "rejected_count": 0,
        })
        scan.setdefault("picks", [])
        scan.setdefault("candidates", [])
        scan["candidates"].append(candidate)
        scan["shadow_count"] = len(scan.get("candidates", []) or [])
        existing_keys.add(key)
        stats.nouveaux_importes += 1
    db["learning"] = build_learning(db)
    agent_weights(db)
    save_db(db)
    stats.total_appris = db["learning"].get("samples", 0)
    stats.poids_agents = dict(db.get("agent_weights", {}))
    return stats


def merge_stats(load_stats: ImportStats, import_stats: ImportStats) -> ImportStats:
    load_stats.candidats_csv = load_stats.candidats_crees
    load_stats.nouveaux_importes = import_stats.nouveaux_importes
    load_stats.deja_presents_ignores = import_stats.deja_presents_ignores
    load_stats.doublons_ignores += import_stats.doublons_ignores
    load_stats.total_appris = import_stats.total_appris
    load_stats.poids_agents = import_stats.poids_agents
    return load_stats


def print_summary(stats: ImportStats, dry_run: bool) -> None:
    print("Résumé import xgabora")
    print(f"- Matchs lus: {stats.matches_lus}")
    print(f"- Matchs ignorés: {stats.matches_ignores}")
    print(f"- Candidats créés: {stats.candidats_crees}")
    print(f"- Candidats créés depuis CSV: {stats.candidats_csv or stats.candidats_crees}")
    print(f"- Candidats déjà présents ignorés: {stats.deja_presents_ignores}")
    print(f"- Nouveaux candidats importés: {stats.nouveaux_importes}")
    print(f"- H2H créés: {stats.h2h_crees}")
    print(f"- Draw créés: {stats.draw_crees}")
    print(f"- Over créés: {stats.over_crees}")
    print(f"- Under créés: {stats.under_crees}")
    print(f"- Over/Under créés: {stats.over_under_crees}")
    print(f"- BTTS créés: {stats.btts_crees}")
    print(f"- Doublons ignorés: {stats.doublons_ignores}")
    print(f"- Date min importée: {stats.date_min_importee or 'aucune'}")
    print(f"- Date max importée: {stats.date_max_importee or 'aucune'}")
    print("- Distribution annuelle importée:")
    if stats.distribution_annuelle:
        for year in sorted(stats.distribution_annuelle):
            print(f"  - {year}: {stats.distribution_annuelle[year]}")
    else:
        print("  - aucune")
    dominant = stats.periode_dominante
    print(f"- Période dominante: {PERIOD_LABELS.get(dominant, dominant or 'aucune')}")
    before_2015 = stats.distribution_periode.get("archive_pre2012", 0) + stats.distribution_periode.get("transition_2012_2014", 0)
    imported_matches = sum(stats.distribution_periode.values())
    if imported_matches and before_2015 / imported_matches > 0.5:
        print("- Avertissement: plus de 50% des matchs importés sont avant 2015, poids réduit recommandé.")
    if dry_run:
        print("- Mode dry-run: aucune sauvegarde effectuée.")
    else:
        print(f"- Total appris après import: {stats.total_appris}")
        print("- Poids agents après import:")
        if stats.poids_agents:
            for agent, weight in stats.poids_agents.items():
                print(f"  - {agent}: {weight}")
        else:
            print("  - aucun poids disponible")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Importe le dataset xgabora MATCHES.csv dans la mémoire Oracle Bot.")
    parser.add_argument("csv_path", help="Chemin vers MATCHES.csv")
    parser.add_argument("--limit", type=int, default=None, help="Nombre maximal de matchs lus")
    parser.add_argument("--from", dest="date_from", default=None, help="Date minimale YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", default=None, help="Date maximale YYYY-MM-DD")
    parser.add_argument("--competitions", default=None, help="Divisions séparées par virgules, ex: E0,SP1,I1,D1,F1")
    parser.add_argument("--dry-run", action="store_true", help="Analyse le CSV sans sauvegarder")
    parser.add_argument("--inspect-columns", action="store_true", help="Inspecte les colonnes Over/Under sur les 1000 premières lignes sans importer")
    parser.add_argument("--inspect-dates", action="store_true", help="Inspecte dates, scores et cotes sans importer")
    return parser.parse_args(argv)


def inspect_columns(csv_path: str, limit: int = 1000) -> None:
    watched = ("Over25", "Under25", "MaxOver25", "MaxUnder25")
    counts = {column: 0 for column in watched}
    rows = 0
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        print("Diagnostic colonnes xgabora")
        print("- Colonnes détectées: " + ", ".join(reader.fieldnames or []))
        for row in reader:
            if rows >= limit:
                break
            rows += 1
            for column in watched:
                if parse_float(row.get(column)) is not None:
                    counts[column] += 1
    print(f"- Lignes inspectées: {rows}")
    for column in watched:
        print(f"- Valeurs numériques {column}: {counts[column]}")


def inspect_dates(csv_path: str) -> Dict[str, Any]:
    report = {
        "total_lignes": 0,
        "matchs_score_final": 0,
        "date_min": "",
        "date_max": "",
        "distribution_annuelle": {},
        "matchs_h2h_odds": 0,
        "matchs_over_under": 0,
        "matchs_btts": 0,
        "colonnes": {},
    }
    with Path(csv_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        fieldnames = reader.fieldnames or []
        report["colonnes"] = {
            "dates": [c for c in DATE_COLUMNS if c in fieldnames],
            "scores_home": [c for c in SCORE_HOME_COLUMNS if c in fieldnames],
            "scores_away": [c for c in SCORE_AWAY_COLUMNS if c in fieldnames],
            "h2h_odds": [c for c in ("OddHome", "OddDraw", "OddAway", "MaxHome", "MaxDraw", "MaxAway") if c in fieldnames],
            "over_under": [c for c in ("Over25", "Under25", "MaxOver25", "MaxUnder25") if c in fieldnames],
            "btts": [c for c in (*BTTS_YES_COLUMNS, *BTTS_NO_COLUMNS) if c in fieldnames],
        }
        for row in reader:
            report["total_lignes"] += 1
            date_key = parse_date(_value(row, *DATE_COLUMNS))
            home_goals = parse_int(_value(row, *SCORE_HOME_COLUMNS))
            away_goals = parse_int(_value(row, *SCORE_AWAY_COLUMNS))
            if date_key:
                report["date_min"] = min(report["date_min"], date_key) if report["date_min"] else date_key
                report["date_max"] = max(report["date_max"], date_key) if report["date_max"] else date_key
                year = date_key[:4]
                report["distribution_annuelle"][year] = report["distribution_annuelle"].get(year, 0) + 1
            if home_goals is not None and away_goals is not None:
                report["matchs_score_final"] += 1
            if has_h2h_odds(row):
                report["matchs_h2h_odds"] += 1
            if has_over_under_odds(row):
                report["matchs_over_under"] += 1
            if has_btts_odds(row):
                report["matchs_btts"] += 1
    return report


def print_date_inspection(report: Dict[str, Any]) -> None:
    print("Diagnostic dates xgabora")
    print(f"- Nombre total de lignes: {report['total_lignes']}")
    print(f"- Matchs avec score final: {report['matchs_score_final']}")
    print(f"- Date min: {report['date_min'] or 'inconnue'}")
    print(f"- Date max: {report['date_max'] or 'inconnue'}")
    print(f"- Matchs avec cotes H2H exploitables: {report['matchs_h2h_odds']}")
    print(f"- Matchs avec Over/Under exploitables: {report['matchs_over_under']}")
    print(f"- Matchs avec BTTS exploitables: {report['matchs_btts']}")
    print("- Colonnes détectées:")
    for key, columns in report["colonnes"].items():
        print(f"  - {key}: {', '.join(columns) if columns else 'aucune'}")
    print("- Distribution par année:")
    for year in sorted(report["distribution_annuelle"]):
        print(f"  - {year}: {report['distribution_annuelle'][year]}")


def main(argv=None):
    args = parse_args(argv)
    if args.inspect_columns:
        inspect_columns(args.csv_path)
        return
    if args.inspect_dates:
        print_date_inspection(inspect_dates(args.csv_path))
        return
    competitions = args.competitions.split(",") if args.competitions else None
    candidates, load_stats = load_candidates(args.csv_path, args.limit, args.date_from, args.date_to, competitions)
    import_stats = import_candidates(candidates, args.dry_run)
    print_summary(merge_stats(load_stats, import_stats), args.dry_run)


if __name__ == "__main__":
    main()
