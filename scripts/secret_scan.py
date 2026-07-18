import argparse
import re
from pathlib import Path


SECRET_NAMES = {
    "API_FOOTBALL_KEY",
    "OPENAI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "DATABASE_URL",
    "THE_ODDS_API_KEY",
    "ODDS_API_KEY",
    "ODDSPAPI_KEY",
    "RAILWAY_TOKEN",
    "GITHUB_TOKEN",
}

SKIP_DIRS = {".git", "__pycache__", "reports", "external_data", "data", "variable", ".venv", "venv"}
SKIP_FILE_PREFIXES = ("oracle_db", "oracle_export_backup")
SKIP_FILE_SUFFIXES = (".pyc",)
ALLOWED_PLACEHOLDERS = {
    "",
    "0",
    "false",
    "true",
    "changeme",
    "change_me",
    "replace_me",
    "placeholder",
    "example",
    "fake",
    "not_configured",
    "your_value_here",
}

ENV_ASSIGNMENT = re.compile(r"^\s*([A-Z0-9_]+)=(.*)\s*$")
TELEGRAM_TOKEN_SHAPE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")


def _is_placeholder(value: str) -> bool:
    cleaned = value.strip().strip("'\"")
    lowered = cleaned.lower()
    if lowered in ALLOWED_PLACEHOLDERS:
        return True
    if "localhost" in lowered and ("password" in lowered or "user" in lowered):
        return True
    return lowered.startswith("replace_me") or lowered.startswith("your_") or lowered.endswith("_example")


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = {part.lower() for part in path.relative_to(root).parts}
        if parts & SKIP_DIRS:
            continue
        name = path.name.lower()
        if name.startswith(SKIP_FILE_PREFIXES) or name.endswith(SKIP_FILE_SUFFIXES):
            continue
        yield path


def scan_file(root: Path, path: Path) -> list[str]:
    findings: list[str] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    rel = str(path.relative_to(root)).replace("\\", "/")
    if TELEGRAM_TOKEN_SHAPE.search(text):
        findings.append(f"{rel}: forme de token Telegram probable")
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = ENV_ASSIGNMENT.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        if key in SECRET_NAMES and not _is_placeholder(value):
            findings.append(f"{rel}:{line_number}: valeur sensible probable pour {key}")
    return findings


def scan(root: Path) -> list[str]:
    root = root.resolve()
    findings: list[str] = []
    for path in iter_files(root):
        findings.extend(scan_file(root, path))
    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Scan local de secrets sans afficher les valeurs.")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    findings = scan(Path(args.root))
    print("Secret scan Oracle")
    print(f"- Fichiers problematiques: {len(findings)}")
    for finding in findings:
        print(f"- {finding}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
