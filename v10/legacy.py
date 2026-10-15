import csv
import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from v10.replay.engine import infer_endpoint, load_json_limited, replay_provider_file


DEFAULT_SCAN_DIRS = ("tests/fixtures", "reports", "external_data", "data")
DEFAULT_MAX_BYTES = 5_000_000


def _kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    return "unknown"


def infer_provider_from_path(path: str) -> str | None:
    text = str(path).replace("\\", "/").lower()
    if "api_football" in text or "api-football" in text:
        return "api_football"
    if "the_odds" in text or "odds_api" in text:
        return "the_odds_api"
    return None


def discover_legacy_sources(root: str = ".", max_bytes: int = DEFAULT_MAX_BYTES) -> dict[str, Any]:
    base = Path(root)
    files = []
    for directory in DEFAULT_SCAN_DIRS:
        source_dir = base / directory
        if not source_dir.exists():
            continue
        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue
            size = path.stat().st_size
            kind = _kind(path)
            if kind == "unknown":
                continue
            files.append(
                {
                    "path": str(path),
                    "size_bytes": size,
                    "kind": kind,
                    "provider_guess": infer_provider_from_path(str(path)),
                    "skipped": size > max_bytes,
                    "skip_reason": "too_large" if size > max_bytes else "",
                }
            )
    return {
        "root": str(base.resolve()),
        "max_bytes": max_bytes,
        "files": sorted(files, key=lambda item: (item["skipped"], item["path"]))[:500],
        "total_found": len(files),
        "too_large": sum(1 for item in files if item["skipped"]),
        "lab_only": True,
        "can_influence_picks": False,
    }


def _count_csv(path: Path) -> int:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        rows = sum(1 for _ in reader)
    return max(0, rows - 1)


def _count_jsonl(path: Path) -> int:
    with path.open(encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def legacy_import_dry_run(source: str, max_bytes: int = DEFAULT_MAX_BYTES, provider: str | None = None) -> dict[str, Any]:
    path = Path(source)
    if not path.exists() or not path.is_file():
        return {"ok": False, "errors": [f"source introuvable: {source}"], "dry_run": True}
    size = path.stat().st_size
    kind = _kind(path)
    if size > max_bytes:
        return {"ok": False, "source": source, "kind": kind, "size_bytes": size, "dry_run": True, "errors": ["file_too_large"], "skipped": True}
    provider = provider or infer_provider_from_path(str(path))
    report: dict[str, Any] = {"ok": True, "source": source, "kind": kind, "size_bytes": size, "provider_guess": provider, "dry_run": True}
    if kind == "csv":
        report["rows"] = _count_csv(path)
    elif kind == "jsonl":
        report["objects"] = _count_jsonl(path)
    elif kind == "json":
        payload = load_json_limited(str(path), max_bytes=max_bytes)
        report["endpoint_guess"] = infer_endpoint(provider or "unknown", payload) if provider else ""
        if isinstance(payload, dict) and isinstance(payload.get("response"), list):
            report["objects"] = len(payload["response"])
        elif isinstance(payload, list):
            report["objects"] = len(payload)
        else:
            report["objects"] = 1
    else:
        report["ok"] = False
        report["errors"] = ["format_non_supporte"]
    return report


def legacy_import_source(
    session: Session | None,
    source: str,
    apply: bool = False,
    provider: str | None = None,
    observed_at: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    dry = legacy_import_dry_run(source, max_bytes=max_bytes, provider=provider)
    if not apply:
        return dry
    if not dry.get("ok"):
        return {**dry, "applied": False}
    provider = provider or dry.get("provider_guess")
    if not provider:
        return {**dry, "applied": False, "errors": ["provider_inconnu_pour_apply"]}
    if dry.get("kind") != "json":
        return {**dry, "applied": False, "errors": ["seul_json_provider_replay_supporte_en_apply"]}
    if session is None:
        return {**dry, "applied": False, "errors": ["session_db_requise"]}
    return replay_provider_file(session, source, provider, observed_at=observed_at, apply=True)

