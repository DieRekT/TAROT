"""SQLite storage for reading sessions with deterministic shuffle support."""

import os
import sqlite3
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional, Any

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "readings.db")


def init_db() -> None:
    """Initialize the readings database with required tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                reading_id TEXT PRIMARY KEY,
                mode TEXT NOT NULL CHECK (mode IN ('physical', 'digital')),
                spread_id TEXT NOT NULL,
                seed TEXT NOT NULL,
                created_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reading_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_id TEXT NOT NULL,
                slot TEXT NOT NULL,
                card_id TEXT NOT NULL,
                reversed BOOLEAN NOT NULL,
                FOREIGN KEY (reading_id) REFERENCES readings (reading_id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()


def create_reading(mode: str, spread_id: str, seed: Optional[str] = None, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Create a new reading session."""
    if seed is None:
        import secrets
        seed = secrets.token_urlsafe(16)
    
    reading_id = str(uuid.uuid4())
    created_at = datetime.utcnow().isoformat()
    
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            INSERT INTO readings (reading_id, mode, spread_id, seed, created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (reading_id, mode, spread_id, seed, created_at, json.dumps(metadata or {})))
        conn.commit()
    
    return {
        "reading_id": reading_id,
        "mode": mode,
        "spread_id": spread_id,
        "seed": seed,
        "created_at": created_at
    }


def get_reading(reading_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a reading by ID."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT reading_id, mode, spread_id, seed, created_at, metadata
            FROM readings WHERE reading_id = ?
        """, (reading_id,))
        row = cursor.fetchone()
        
        if not row:
            return None
        
        reading = dict(row)
        reading["metadata"] = json.loads(reading["metadata"] or "{}")
        
        # Get positions if they exist
        cursor = conn.execute("""
            SELECT slot, card_id, reversed FROM reading_positions
            WHERE reading_id = ? ORDER BY id
        """, (reading_id,))
        positions = []
        for row in cursor.fetchall():
            pos = dict(row)
            # Convert SQLite integer (0/1) back to boolean
            pos["reversed"] = bool(pos["reversed"])
            positions.append(pos)
        reading["positions"] = positions
        
        return reading


def save_positions(reading_id: str, positions: List[Dict[str, Any]], force_redraw: bool = False) -> None:
    """Save card positions for a reading."""
    with sqlite3.connect(DB_PATH) as conn:
        # Check if positions already exist
        cursor = conn.execute("""
            SELECT COUNT(*) FROM reading_positions WHERE reading_id = ?
        """, (reading_id,))
        has_positions = cursor.fetchone()[0] > 0
        
        if has_positions and not force_redraw:
            raise ValueError("Positions already exist for this reading. Use force_redraw to overwrite.")
        
        # Delete existing positions if force_redraw
        if force_redraw:
            conn.execute("""
                DELETE FROM reading_positions WHERE reading_id = ?
            """, (reading_id,))
        
        # Insert new positions
        for pos in positions:
            conn.execute("""
                INSERT INTO reading_positions (reading_id, slot, card_id, reversed)
                VALUES (?, ?, ?, ?)
            """, (reading_id, pos["slot"], pos["card_id"], pos["reversed"]))
        
        conn.commit()


def get_all_readings(limit: int = 100) -> List[Dict[str, Any]]:
    """Get all readings (for debugging/admin)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT reading_id, mode, spread_id, seed, created_at, metadata
            FROM readings ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        readings = [dict(row) for row in cursor.fetchall()]
        
        # Parse metadata for each reading
        for reading in readings:
            reading["metadata"] = json.loads(reading["metadata"] or "{}")
        
        return readings
