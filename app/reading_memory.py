"""Reading conversation memory using SQLite."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

DB_PATH = Path(__file__).resolve().parent / "data" / "reading_memory.sqlite"

def _init_db() -> sqlite3.Connection:
    """Initialize database and create tables if needed."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reading_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reading_id TEXT NOT NULL,
            ts INTEGER NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
            content TEXT NOT NULL,
            cards_json TEXT,
            overlay TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reading_id ON reading_messages(reading_id)")
    conn.commit()
    return conn

def append_message(reading_id: str, role: str, content: str, cards: List[Dict[str, Any]], overlay: Optional[str] = None) -> None:
    """Append a message to reading history."""
    conn = _init_db()
    try:
        conn.execute(
            "INSERT INTO reading_messages (reading_id, ts, role, content, cards_json, overlay) VALUES (?, ?, ?, ?, ?, ?)",
            (reading_id, int(time.time()), role, content, json.dumps(cards), overlay)
        )
        conn.commit()
    finally:
        conn.close()

def get_history(reading_id: str, limit: int = 30) -> List[Dict[str, str]]:
    """Get conversation history for a reading."""
    conn = _init_db()
    try:
        cursor = conn.execute(
            "SELECT role, content FROM reading_messages WHERE reading_id = ? ORDER BY ts ASC LIMIT ?",
            (reading_id, limit)
        )
        return [{"role": row[0], "content": row[1]} for row in cursor.fetchall()]
    finally:
        conn.close()

def reset_reading(reading_id: str) -> None:
    """Clear all messages for a reading."""
    conn = _init_db()
    try:
        conn.execute("DELETE FROM reading_messages WHERE reading_id = ?", (reading_id,))
        conn.commit()
    finally:
        conn.close()

def prune_old(max_days: int = 30) -> None:
    """Remove messages older than max_days."""
    cutoff_ts = int(time.time()) - (max_days * 24 * 3600)
    conn = _init_db()
    try:
        conn.execute("DELETE FROM reading_messages WHERE ts < ?", (cutoff_ts,))
        conn.commit()
    finally:
        conn.close()
