import argparse
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from external_dataset_probe import profile_file, profile_folder


def _detected(profile: Dict, key: str) -> List[str]:
    return (profile.get("detected_columns") or {}).get(key, []) or []


def _profile_items(path: str) -> List[Dict]:
    target = Path(path)
    if target.is_dir():
        return profile_folder(path).get("files", []) or []
    return [profile_file(path)]


def build_epl_fbref_report(path: str) -> Dict:
    profiles = _profile_items(path)
    files = []
    capabilities = {
        "matches": [],
        "team_stats": [],
        "player_stats": [],
        "xg": [],
        "xga": [],
        "shots": [],
        "shots_on_target": [],
        "lineups": [],
        "match_ids": [],
        "team_names": [],
        "dates": [],
    }
    for profile in profiles:
        file_path = profile.get("path", "")
        columns = profile.get("columns", [])
        normalized = {str(column).lower(): column for column in columns}
        if _detected(profile, "date") and _detected(profile, "home_team") and _detected(profile, "away_team"):
            capabilities["matches"].append(file_path)
        if _detected(profile, "team_stats"):
            capabilities["team_stats"].append(file_path)
        if _detected(profile, "player_stats"):
            capabilities["player_stats"].append(file_path)
        if _detected(profile, "xg"):
            capabilities["xg"].append(file_path)
        if any("xga" in key or "against" in key for key in normalized):
            capabilities["xga"].append(file_path)
        if _detected(profile, "shots"):
            capabilities["shots"].append(file_path)
        if _detected(profile, "shots_on_target"):
            capabilities["shots_on_target"].append(file_path)
        if _detected(profile, "lineups"):
            capabilities["lineups"].append(file_path)
        if any("matchid" in key.replace("_", "") or key == "id" for key in normalized):
            capabilities["match_ids"].append(file_path)
        if _detected(profile, "home_team") or _detected(profile, "away_team") or _detected(profile, "team_stats"):
            capabilities["team_names"].append(file_path)
        if _detected(profile, "date"):
            capabilities["dates"].append(file_path)
        files.append({
            "path": file_path,
            "rows": profile.get("rows", 0),
            "columns": profile.get("columns_count", 0),
            "detected": profile.get("detected_columns", {}),
            "utility": profile.get("utility", {}),
            "timing": profile.get("timing", {}),
        })
    join_possible = {
        "date": bool(capabilities["dates"]),
        "home_team": any(_detected(profile, "home_team") for profile in profiles),
        "away_team": any(_detected(profile, "away_team") for profile in profiles),
        "competition": any(_detected(profile, "competition") for profile in profiles),
    }
    return {
        "path": path,
        "files": files,
        "capabilities": capabilities,
        "join_possible": join_possible,
        "risks": [
            "noms d'equipes differents entre FBref/Kaggle et xgabora",
            "dates exprimees dans un fuseau ou un format different",
            "xG, tirs, tirs cadres et stats de match sont souvent post-match",
            "lineups finales peuvent etre connues tard et doivent etre marquees comme risque",
            "absence de cotes: ne remplace pas xgabora",
        ],
    }


def print_report(report: Dict) -> None:
    print("Adaptateur laboratoire EPL FBref")
    print(f"- Source locale: {report.get('path')}")
    print(f"- Fichiers detectes: {len(report.get('files') or [])}")
    for file in report.get("files") or []:
        print(f"\nFichier: {file.get('path')}")
        print(f"- Lignes: {file.get('rows', 0)}")
        print(f"- Colonnes: {file.get('columns', 0)}")
        detected = file.get("detected") or {}
        for key in ("date", "home_team", "away_team", "score", "xg", "shots", "shots_on_target", "lineups", "player_stats", "odds"):
            if detected.get(key):
                print(f"- {key}: {', '.join(detected[key][:8])}")
    print("\nCapacites detectees")
    for key, files in (report.get("capabilities") or {}).items():
        print(f"- {key}: {len(files)} fichier(s)")
    print("\nPossibilite de jointure avec xgabora")
    join = report.get("join_possible") or {}
    print(f"- date: {'oui' if join.get('date') else 'non'}")
    print(f"- home_team: {'oui' if join.get('home_team') else 'non'}")
    print(f"- away_team: {'oui' if join.get('away_team') else 'non'}")
    print(f"- competition: {'oui' if join.get('competition') else 'non'}")
    print("\nRisques")
    for risk in report.get("risks") or []:
        print(f"- {risk}")
    print("- Rappel: cet adaptateur ne telecharge rien et ne modifie aucune memoire.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Profile un dataset EPL/FBref local sans telechargement.")
    parser.add_argument("--profile", required=True, help="Fichier ou dossier local a profiler")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    print_report(build_epl_fbref_report(args.profile))


if __name__ == "__main__":
    main()
