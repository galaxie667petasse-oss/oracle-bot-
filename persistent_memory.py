import json
import os
from typing import Any, Dict, Optional

DB_KEY = "oracle_main_memory"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def enabled() -> bool:
    return bool(DATABASE_URL)


def _connect():
    import psycopg
    return psycopg.connect(DATABASE_URL)


def ensure_table() -> None:
    if not enabled():
        return
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS oracle_memory (
                    key TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()


def load_remote() -> Optional[Dict[str, Any]]:
    if not enabled():
        return None
    ensure_table()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM oracle_memory WHERE key = %s", (DB_KEY,))
            row = cur.fetchone()
            if not row:
                return None
            data = row[0]
            if isinstance(data, str):
                return json.loads(data)
            return data


def save_remote(data: Dict[str, Any]) -> None:
    if not enabled():
        return
    from psycopg.types.json import Jsonb

    ensure_table()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO oracle_memory (key, data, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key)
                DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()
                """,
                (DB_KEY, Jsonb(data)),
            )
        conn.commit()


def status() -> Dict[str, Any]:
    if not enabled():
        return {"enabled": False, "message": "DATABASE_URL absent : mémoire locale seulement"}
    try:
        ensure_table()
        return {"enabled": True, "message": "PostgreSQL actif : mémoire persistante"}
    except Exception as exc:
        return {"enabled": False, "message": f"PostgreSQL indisponible : {exc}"}
