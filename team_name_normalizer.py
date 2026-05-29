import csv
import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


ALIASES = {
    "man united": "manchester united",
    "man utd": "manchester united",
    "manchester utd": "manchester united",
    "man u": "manchester united",
    "man city": "manchester city",
    "manchester city": "manchester city",
    "spurs": "tottenham",
    "tottenham hotspur": "tottenham",
    "wolves": "wolverhampton",
    "wolverhampton wanderers": "wolverhampton",
    "newcastle utd": "newcastle",
    "newcastle united": "newcastle",
    "nottm forest": "nottingham forest",
    "nott m forest": "nottingham forest",
    "nott ham forest": "nottingham forest",
    "nottingham forest": "nottingham forest",
    "ipswich town": "ipswich",
    "leicester city": "leicester",
    "brighton hove": "brighton hove albion",
    "brighton and hove albion": "brighton hove albion",
}

LEAGUE_ALIASES = {
    "la_liga": {
        "atletico madrid": "atletico madrid",
        "athletico madrid": "atletico madrid",
        "atl madrid": "atletico madrid",
        "athletic": "athletic bilbao",
        "ath bilbao": "athletic bilbao",
        "athletic club": "athletic bilbao",
        "athletic bilbao": "athletic bilbao",
        "betis": "real betis",
        "real betis": "real betis",
        "ath madrid": "atletico madrid",
        "sevilla": "sevilla",
        "sevilla fc": "sevilla",
        "real sociedad": "real sociedad",
        "sociedad": "real sociedad",
        "celta vigo": "celta vigo",
        "celta": "celta vigo",
        "alaves": "alaves",
        "cadiz": "cadiz",
        "leganes": "leganes",
        "mallorca": "mallorca",
        "real mallorca": "mallorca",
        "rayo vallecano": "rayo vallecano",
        "vallecano": "rayo vallecano",
        "valladolid": "valladolid",
        "real valladolid": "valladolid",
        "espanyol": "espanyol",
        "espanol": "espanyol",
        "girona": "girona",
        "girona fc": "girona",
        "osasuna": "osasuna",
        "ca osasuna": "osasuna",
        "huesca": "huesca",
        "sd huesca": "huesca",
    },
    "bundesliga": {
        "bayer leverkusen": "leverkusen",
        "leverkusen": "leverkusen",
        "eintracht frankfurt": "ein frankfurt",
        "ein frankfurt": "ein frankfurt",
        "frankfurt": "ein frankfurt",
        "heidenheim": "heidenheim",
        "heidenheim 1846": "heidenheim",
        "fc heidenheim": "heidenheim",
        "1 heidenheim": "heidenheim",
        "borussia dortmund": "dortmund",
        "dortmund": "dortmund",
        "borussia m gladbach": "mgladbach",
        "borussia mgladbach": "mgladbach",
        "borussia monchengladbach": "mgladbach",
        "monchengladbach": "mgladbach",
        "m gladbach": "mgladbach",
        "mgladbach": "mgladbach",
        "gladbach": "mgladbach",
        "rb leipzig": "rb leipzig",
        "rasenballsport leipzig": "rb leipzig",
        "leipzig": "rb leipzig",
        "bayern munich": "bayern munich",
        "bayern munchen": "bayern munich",
        "fc bayern munchen": "bayern munich",
        "bayern": "bayern munich",
        "freiburg": "freiburg",
        "sc freiburg": "freiburg",
        "hoffenheim": "hoffenheim",
        "tsg hoffenheim": "hoffenheim",
        "wolfsburg": "wolfsburg",
        "vfl wolfsburg": "wolfsburg",
        "werder bremen": "werder bremen",
        "bremen": "werder bremen",
        "union berlin": "union berlin",
        "1 union berlin": "union berlin",
        "1 fc union berlin": "union berlin",
        "st pauli": "st pauli",
        "fc st pauli": "st pauli",
        "holstein kiel": "holstein kiel",
        "kiel": "holstein kiel",
        "hertha berlin": "hertha",
        "hertha bsc": "hertha",
        "hertha": "hertha",
        "schalke 04": "schalke 04",
        "fc schalke 04": "schalke 04",
        "koln": "koln",
        "cologne": "koln",
        "fc cologne": "koln",
        "fc koln": "koln",
        "1 koln": "koln",
        "mainz 05": "mainz",
        "fsv mainz 05": "mainz",
        "mainz": "mainz",
        "augsburg": "augsburg",
        "fc augsburg": "augsburg",
        "stuttgart": "stuttgart",
        "vfb stuttgart": "stuttgart",
        "bochum": "bochum",
        "vfl bochum": "bochum",
        "darmstadt": "darmstadt",
        "sv darmstadt 98": "darmstadt",
        "arminia bielefeld": "bielefeld",
        "bielefeld": "bielefeld",
        "greuther furth": "greuther furth",
        "greuther fuerth": "greuther furth",
        "fuerth": "greuther furth",
        "furth": "greuther furth",
    },
    "serie_a": {
        "internazionale": "inter",
        "inter milan": "inter",
        "inter": "inter",
        "ac milan": "milan",
        "milan": "milan",
        "juventus": "juventus",
        "juve": "juventus",
        "roma": "roma",
        "as roma": "roma",
        "lazio": "lazio",
        "napoli": "napoli",
        "ssc napoli": "napoli",
        "atalanta": "atalanta",
        "atalanta bc": "atalanta",
        "fiorentina": "fiorentina",
        "acf fiorentina": "fiorentina",
        "sassuolo": "sassuolo",
        "us sassuolo": "sassuolo",
        "bologna": "bologna",
        "bologna 1909": "bologna",
        "torino": "torino",
        "torino 1906": "torino",
        "udinese": "udinese",
        "udinese calcio": "udinese",
        "sampdoria": "sampdoria",
        "genoa": "genoa",
        "genoa cfc": "genoa",
        "cagliari": "cagliari",
        "cagliari calcio": "cagliari",
        "verona": "verona",
        "hellas verona": "verona",
        "spezia": "spezia",
        "spezia calcio": "spezia",
        "empoli": "empoli",
        "venezia": "venezia",
        "venezia fc": "venezia",
        "salernitana": "salernitana",
        "us salernitana": "salernitana",
        "lecce": "lecce",
        "us lecce": "lecce",
        "monza": "monza",
        "ac monza": "monza",
        "cremonese": "cremonese",
        "us cremonese": "cremonese",
        "parma": "parma",
        "parma calcio 1913": "parma",
        "benevento": "benevento",
        "crotone": "crotone",
        "frosinone": "frosinone",
        "frosinone calcio": "frosinone",
        "como": "como",
        "como 1907": "como",
    },
    "ligue_1": {
        "paris saint germain": "paris sg",
        "psg": "paris sg",
        "paris sg": "paris sg",
        "marseille": "marseille",
        "olympique marseille": "marseille",
        "lyon": "lyon",
        "olympique lyonnais": "lyon",
        "monaco": "monaco",
        "as monaco": "monaco",
        "lille": "lille",
        "losc lille": "lille",
        "rennes": "rennes",
        "stade rennes": "rennes",
        "nice": "nice",
        "ogc nice": "nice",
        "lens": "lens",
        "rc lens": "lens",
        "strasbourg": "strasbourg",
        "reims": "reims",
        "stade de reims": "reims",
        "montpellier": "montpellier",
        "nantes": "nantes",
        "fc nantes": "nantes",
        "bordeaux": "bordeaux",
        "girondins bordeaux": "bordeaux",
        "saint etienne": "st etienne",
        "as saint etienne": "st etienne",
        "st etienne": "st etienne",
        "angers sco": "angers",
        "angers": "angers",
        "brest": "brest",
        "stade brestois": "brest",
        "metz": "metz",
        "fc metz": "metz",
        "lorient": "lorient",
        "fc lorient": "lorient",
        "troyes": "troyes",
        "estac troyes": "troyes",
        "clermont foot": "clermont",
        "clermont": "clermont",
        "auxerre": "auxerre",
        "aj auxerre": "auxerre",
        "toulouse": "toulouse",
        "toulouse fc": "toulouse",
        "le havre": "le havre",
        "le havre ac": "le havre",
        "ajaccio": "ajaccio",
        "ac ajaccio": "ajaccio",
        "dijon": "dijon",
        "dijon fco": "dijon",
        "nimes": "nimes",
        "amiens": "amiens",
        "amiens sc": "amiens",
        "montpellier hsc": "montpellier",
        "rc strasbourg": "strasbourg",
        "sochaux": "sochaux",
        "fc sochaux": "sochaux",
        "fc sochaux montbeliard": "sochaux",
        "sochaux montbeliard": "sochaux",
        "guingamp": "guingamp",
        "ea guingamp": "guingamp",
        "en avant guingamp": "guingamp",
        "caen": "caen",
        "sm caen": "caen",
        "stade malherbe caen": "caen",
    },
}

for _league_aliases in LEAGUE_ALIASES.values():
    for _alias, _canonical in _league_aliases.items():
        ALIASES.setdefault(_alias, _canonical)

STOP_WORDS = {
    "fc",
    "afc",
    "cf",
    "sc",
    "club",
    "football",
    "the",
}


def _ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _clean_words(name: object) -> str:
    text = _ascii(str(name or "")).lower()
    text = text.replace("&", " and ")
    text = text.replace("'", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = [word for word in text.split() if word not in STOP_WORDS]
    return " ".join(words)


def _league_key(league: Optional[object]) -> str:
    text = _clean_words(league)
    if text in {"la liga", "laliga", "esp la liga", "spain", "espana"}:
        return "la_liga"
    if text in {"epl", "premier league", "eng premier league", "england"}:
        return "epl"
    if text in {"bundesliga", "ger bundesliga", "germany bundesliga", "germany", "d1"}:
        return "bundesliga"
    if text in {"serie a", "italy serie a", "ita serie a", "italy", "i1"}:
        return "serie_a"
    if text in {"ligue 1", "france ligue 1", "fra ligue 1", "france", "f1"}:
        return "ligue_1"
    if text in {"sp1"}:
        return "la_liga"
    if text in {"e0"}:
        return "epl"
    return text.replace(" ", "_")


def load_alias_file(path: str = "") -> Dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _flatten_aliases(aliases: Optional[Dict[str, Any]], league: Optional[object] = None) -> Dict[str, str]:
    flat: Dict[str, str] = {}
    if not aliases:
        return flat
    for key, value in aliases.items():
        if isinstance(value, str):
            flat[_clean_words(key)] = _clean_words(value)
    league_key = _league_key(league)
    league_data = aliases.get(league_key) or aliases.get(str(league or ""))
    if isinstance(league_data, dict):
        for key, value in league_data.items():
            if isinstance(value, str):
                flat[_clean_words(key)] = _clean_words(value)
    return flat


def apply_aliases(name: object, aliases: Optional[Dict[str, Any]] = None, league: Optional[object] = None) -> str:
    cleaned = _clean_words(name)
    if not cleaned:
        return ""
    custom = _flatten_aliases(aliases, league=league)
    if cleaned in custom:
        return custom[cleaned]
    league_aliases = LEAGUE_ALIASES.get(_league_key(league), {})
    if cleaned in league_aliases:
        return league_aliases[cleaned]
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    return cleaned


def normalize_team_name(name: object, league: Optional[object] = None, aliases: Optional[Dict[str, Any]] = None, use_aliases: bool = True) -> str:
    """Retourne une forme canonique prudente, sans modifier les donnees source."""
    cleaned = _clean_words(name)
    if not cleaned:
        return ""
    if not use_aliases:
        return cleaned
    return apply_aliases(cleaned, aliases=aliases, league=league)


def team_name_similarity(a: object, b: object, league: Optional[object] = None) -> float:
    left = normalize_team_name(a, league=league)
    right = normalize_team_name(b, league=league)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return round(difflib.SequenceMatcher(None, left, right).ratio(), 4)


def suggest_team_aliases(external_names: Iterable[object], xgabora_names: Iterable[object], threshold: float = 0.75, league: Optional[object] = None) -> List[Dict[str, object]]:
    suggestions: List[Dict[str, object]] = []
    xgabora_list = sorted({str(name or "").strip() for name in xgabora_names if str(name or "").strip()})
    for external_name in sorted({str(name or "").strip() for name in external_names if str(name or "").strip()}):
        best_name = ""
        best_score = 0.0
        for xgabora_name in xgabora_list:
            score = team_name_similarity(external_name, xgabora_name, league=league)
            if score > best_score:
                best_name = xgabora_name
                best_score = score
        if best_name and best_score >= threshold:
            suggestions.append({
                "external_name": external_name,
                "suggested_xgabora_name": best_name,
                "similarity": best_score,
                "normalized_external": normalize_team_name(external_name, league=league),
                "normalized_xgabora": normalize_team_name(best_name, league=league),
                "status": "suggestion_a_valider",
            })
    return suggestions


def suggest_team_matches(external_names: Iterable[object], xgabora_names: Iterable[object], threshold: float = 0.72) -> List[Dict[str, object]]:
    return suggest_team_aliases(external_names, xgabora_names, threshold=threshold)


def export_team_mapping_suggestions(suggestions: Iterable[Dict[str, object]], output: str = "reports/team_mapping_suggestions.csv") -> Path:
    target = Path(output)
    if "reports" not in [part.lower() for part in target.parts]:
        raise ValueError("Le mapping manuel doit etre exporte dans reports/.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "external_name",
        "suggested_xgabora_name",
        "similarity",
        "normalized_external",
        "normalized_xgabora",
        "status",
    ]
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for suggestion in suggestions:
            writer.writerow({key: suggestion.get(key, "") for key in fieldnames})
    return target
