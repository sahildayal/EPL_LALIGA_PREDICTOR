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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS player_statistics (
            player_name TEXT PRIMARY KEY,
            position TEXT NOT NULL,
            xg_per_90 REAL NOT NULL,
            goals_per_90 REAL NOT NULL,
            assists_per_90 REAL NOT NULL,
            club_team TEXT,
            intl_team TEXT,
            last_updated REAL NOT NULL
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


def save_player_stats(player_name: str, position: str, xg_per_90: float, goals_per_90: float, assists_per_90: float, club_team: str, intl_team: str):
    name_lower = player_name.lower().strip()
    try:
        conn = _conn()
        try:
            with conn:
                conn.execute("""
                    INSERT OR REPLACE INTO player_statistics 
                    (player_name, position, xg_per_90, goals_per_90, assists_per_90, club_team, intl_team, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (name_lower, position, xg_per_90, goals_per_90, assists_per_90, 
                      club_team.lower().strip() if club_team else "", 
                      intl_team.lower().strip() if intl_team else "", 
                      time.time()))
        finally:
            conn.close()
    except Exception:
        pass


def get_player_stats_cache(player_name: str) -> dict | None:
    name_lower = player_name.lower().strip()
    try:
        conn = _conn()
        try:
            with conn:
                row = conn.execute("""
                    SELECT position, xg_per_90, goals_per_90, assists_per_90, club_team, intl_team, last_updated
                    FROM player_statistics WHERE player_name = ?
                """, (name_lower,)).fetchone()
            if row:
                # Check TTL of 7 days (604800 seconds)
                if time.time() - row[6] < 604800:
                    return {
                        "name": name_lower,
                        "position": row[0],
                        "xg_per_90": row[1],
                        "goals_per_90": row[2],
                        "assists_per_90": row[3],
                        "club_team": row[4],
                        "intl_team": row[5]
                    }
        finally:
            conn.close()
    except Exception:
        pass
    return None
