"""Separate additive SQLite read model; never migrates or writes the V10 database.

Content-addressed source snapshots, sealed predictions and separate outcome events.
SQLite triggers reject UPDATE/DELETE even outside this repository API. Hashes detect
accidental corruption, not tampering by an administrator with filesystem access.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


def encode(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(payload: dict) -> str:
    return hashlib.sha256(encode(payload).encode()).hexdigest()


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in {0, 1}:
                raise ValueError("unsupported V11 schema version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY, captured_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS predictions (
                    id TEXT PRIMARY KEY, fixture_id TEXT NOT NULL, kickoff TEXT NOT NULL,
                    decision_at TEXT NOT NULL, snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS outcomes (
                    id TEXT PRIMARY KEY, prediction_id TEXT NOT NULL REFERENCES predictions(id),
                    observed_at TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS prediction_date ON predictions(kickoff);
                PRAGMA user_version=1;
            """)
            for table in ("snapshots", "predictions", "outcomes"):
                for operation in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{operation} "
                               f"BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT, 'immutable record'); END")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_snapshot(self, payload: dict) -> str:
        from v11.contracts import Snapshot
        payload = Snapshot.model_validate(payload).model_dump(mode="json")
        key = digest(payload)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO snapshots VALUES(?,?,?)", (key, payload["captured_at"], encode(payload)))
        return key

    def latest_snapshot(self) -> tuple[str, dict] | None:
        with self.connect() as db:
            rows = db.execute("SELECT id,payload FROM snapshots").fetchall()
        return max(((key, json.loads(payload)) for key, payload in rows),
                   key=lambda item: datetime.fromisoformat(item[1]["captured_at"]), default=None)

    def add_prediction(self, payload: dict) -> str:
        decision = datetime.fromisoformat(payload["decision_at"])
        if decision >= datetime.fromisoformat(payload["kickoff"]):
            raise ValueError("prediction must precede kickoff")
        key = digest(payload)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO predictions VALUES(?,?,?,?,?,?)",
                       (key, payload["fixture_id"], payload["kickoff"], payload["decision_at"], payload["snapshot_id"], encode(payload)))
        return key

    def add_outcome(self, prediction_id: str, home: int, away: int, observed_at: datetime,
                    source: str, status: str = "FT") -> str:
        from v10.time import ensure_utc
        from v11.markets import settle
        ensure_utc(observed_at)
        if not source.strip():
            raise ValueError("result source required")
        with self.connect() as db:
            row = db.execute("SELECT payload FROM predictions WHERE id=?", (prediction_id,)).fetchone()
            if row is None:
                raise ValueError("unknown prediction")
            pred = json.loads(row[0])
            if observed_at <= datetime.fromisoformat(pred["kickoff"]):
                raise ValueError("result must be observed after kickoff")
            # Validate even an abstention without quoted markets.
            settle("match_winner", "home", 2.0, home, away, status=status)
            settlements = [{**q, "settlement": settle(q["market"], q["selection"], q["odds"], home, away, q["line"], status).__dict__}
                           for q in pred.get("comparisons", [])]
            payload = {"prediction_id": prediction_id, "home": home, "away": away,
                       "status": status, "observed_at": observed_at.isoformat(), "source": source,
                       "settlements": settlements}
            key = digest(payload)
            db.execute("INSERT OR IGNORE INTO outcomes VALUES(?,?,?,?)", (key, prediction_id, observed_at.isoformat(), encode(payload)))
        return key

    def history(self, limit: int = 100) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT id,payload FROM predictions ORDER BY rowid DESC LIMIT ?", (min(max(limit, 1), 500),)).fetchall()
            return [{"id": key, **json.loads(payload), "outcomes": [json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM outcomes WHERE prediction_id=? ORDER BY rowid", (key,))]} for key, payload in rows]

    def verify(self) -> dict:
        with self.connect() as db:
            integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
            counts = {}
            for table in ("snapshots", "predictions", "outcomes"):
                rows = db.execute(f"SELECT id,payload FROM {table}").fetchall()
                if any(digest(json.loads(payload)) != key for key, payload in rows):
                    raise ValueError(f"hash mismatch in {table}")
                counts[table] = len(rows)
        return {"integrity": integrity, "foreign_keys_ok": not foreign_keys, "hashes_ok": True, "counts": counts}

    def backup(self, target: Path) -> dict:
        if target.exists():
            raise ValueError("backup destination must be new")
        target.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        return Ledger(target).verify()
