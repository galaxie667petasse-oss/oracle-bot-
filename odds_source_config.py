import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_EXAMPLE_PATH = Path("config/odds_sources.example.json")
DEFAULT_LOCAL_PATH = Path("config/odds_sources.json")

EXAMPLE_CONFIG: Dict[str, Any] = {
    "api_football": {
        "enabled": False,
        "base_url": "https://v3.football.api-sports.io",
        "api_key_env": "API_FOOTBALL_KEY",
        "daily_limit": 100,
        "default_bookmakers": [],
        "notes": "Free plan possible, ne pas committer la cle.",
    },
    "the_odds_api": {
        "enabled": False,
        "base_url": "https://api.the-odds-api.com/v4",
        "api_key_env": "THE_ODDS_API_KEY",
        "monthly_credits_limit": 500,
        "regions": "eu",
        "markets": "h2h,totals",
        "odds_format": "decimal",
        "notes": "Free plan limite, historique payant.",
    },
    "manual_csv": {
        "enabled": True,
        "default_path": "reports/manual_odds_snapshot.csv",
    },
}


def write_example(path: str = str(DEFAULT_EXAMPLE_PATH), force: bool = True) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        return target
    target.write_text(json.dumps(EXAMPLE_CONFIG, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _read_config(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("La configuration odds doit etre un objet JSON.")
    return data


def load_odds_source_config(path: Optional[str] = None) -> Dict[str, Any]:
    if path:
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Configuration odds introuvable: {target}")
        return _read_config(target)
    if DEFAULT_LOCAL_PATH.exists():
        return _read_config(DEFAULT_LOCAL_PATH)
    if DEFAULT_EXAMPLE_PATH.exists():
        return _read_config(DEFAULT_EXAMPLE_PATH)
    return json.loads(json.dumps(EXAMPLE_CONFIG))


def get_api_key_from_env(source_name: str, config: Optional[Dict[str, Any]] = None) -> Optional[str]:
    config = config or load_odds_source_config()
    source = config.get(source_name) or {}
    env_name = source.get("api_key_env")
    if not env_name:
        return None
    value = os.getenv(str(env_name), "")
    return value if value else None


def source_enabled(source_name: str, config: Optional[Dict[str, Any]] = None) -> bool:
    config = config or load_odds_source_config()
    return bool((config.get(source_name) or {}).get("enabled"))


def validate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    for source_name in ("api_football", "the_odds_api", "manual_csv"):
        if source_name not in config:
            errors.append(f"source manquante: {source_name}")
    for source_name in ("api_football", "the_odds_api"):
        source = config.get(source_name) or {}
        if source and not source.get("base_url"):
            errors.append(f"{source_name}: base_url manquant")
        if source and not source.get("api_key_env"):
            errors.append(f"{source_name}: api_key_env manquant")
        if source.get("enabled") and not get_api_key_from_env(source_name, config):
            warnings.append(f"{source_name}: active mais cle API absente dans l'environnement")
    manual = config.get("manual_csv") or {}
    if manual and not manual.get("default_path"):
        warnings.append("manual_csv: default_path absent")
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "sources": sorted(config.keys()),
        "lab_only": True,
        "can_influence_picks": False,
    }


def _masked_key_status(source_name: str, config: Dict[str, Any]) -> str:
    source = config.get(source_name) or {}
    env_name = source.get("api_key_env")
    if not env_name:
        return "non configuree"
    return "presente" if os.getenv(str(env_name), "") else "absente"


def show_config(config: Dict[str, Any]) -> None:
    print("Configuration sources de cotes Oracle")
    for name, source in config.items():
        if not isinstance(source, dict):
            print(f"- {name}: configuration invalide")
            continue
        print(f"- {name}: enabled={source.get('enabled')}")
        if source.get("base_url"):
            print(f"  base_url={source.get('base_url')}")
        if source.get("api_key_env"):
            print(f"  cle API: {_masked_key_status(name, config)}")
    print("- Aucun reseau n'est lance par ce module.")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Configuration locale des sources de cotes, sans secrets affiches.")
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--write-example", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--path", default="")
    parser.add_argument("--example-path", default=str(DEFAULT_EXAMPLE_PATH))
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.write_example:
            path = write_example(args.example_path)
            print(f"- Exemple de configuration ecrit: {path}")
            print("- Ne pas committer de fichier contenant une vraie cle API.")
        config = load_odds_source_config(args.path or None)
        if args.show:
            show_config(config)
        if args.check or not (args.show or args.write_example):
            report = validate_config(config)
            show_config(config)
            print(f"- Validation: {'OK' if report['ok'] else 'bloquante'}")
            for warning in report["warnings"]:
                print(f"- Warning: {warning}")
            for error in report["errors"]:
                print(f"- Erreur: {error}")
            return 0 if report["ok"] else 1
        return 0
    except Exception as exc:
        print(f"Erreur: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
