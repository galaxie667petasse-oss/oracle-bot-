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
    }
}

for _alias, _canonical in LEAGUE_ALIASES["la_liga"].items():
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


def team_name_similarity(a: object, b: object) -> float:
    left = normalize_team_name(a)
    right = normalize_team_name(b)
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
            score = team_name_similarity(external_name, xgabora_name)
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
