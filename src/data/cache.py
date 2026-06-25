import sqlite3
import json
import time
import hashlib
from pathlib import Path

DB_PATH = Path(__file__).parent.parent.parent / "data" / "cache" / "worldcup.db"


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _key(namespace: str, params: dict) -> str:
    raw = namespace + json.dumps(params, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def get(namespace: str, params: dict):
    k = _key(namespace, params)
    try:
        conn = _conn()
        try:
            with conn:
                row = conn.execute(
                    "SELECT value, expires_at FROM cache WHERE key = ?", (k,)
                ).fetchone()
            if row and row[1] > time.time():
                return json.loads(row[0])
        finally:
            conn.close()
    except Exception:
        pass
    return None


def set(namespace: str, params: dict, value, ttl_seconds: int = 86400):
    k = _key(namespace, params)
    try:
        conn = _conn()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
                    (k, json.dumps(value), time.time() + ttl_seconds),
                )
        finally:
            conn.close()
    except Exception:
        pass


def invalidate(namespace: str, params: dict):
    k = _key(namespace, params)
    try:
        conn = _conn()
        try:
            with conn:
                conn.execute("DELETE FROM cache WHERE key = ?", (k,))
        finally:
            conn.close()
    except Exception:
        pass


def purge_expired():
    try:
        conn = _conn()
        try:
            with conn:
                conn.execute("DELETE FROM cache WHERE expires_at <= ?", (time.time(),))
        finally:
            conn.close()
    except Exception:
        pass
