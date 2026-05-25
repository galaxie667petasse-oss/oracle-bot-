import csv
import difflib
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List


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


def normalize_team_name(name: object) -> str:
    """Retourne une forme canonique prudente, sans modifier les donnees source."""
    cleaned = _clean_words(name)
    if not cleaned:
        return ""
    if cleaned in ALIASES:
        return ALIASES[cleaned]
    return cleaned


def team_name_similarity(a: object, b: object) -> float:
    left = normalize_team_name(a)
    right = normalize_team_name(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return round(difflib.SequenceMatcher(None, left, right).ratio(), 4)


def suggest_team_matches(external_names: Iterable[object], xgabora_names: Iterable[object], threshold: float = 0.72) -> List[Dict[str, object]]:
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
                "normalized_external": normalize_team_name(external_name),
                "normalized_xgabora": normalize_team_name(best_name),
                "status": "suggestion_a_valider",
            })
    return suggestions


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
