
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "ai_scientist.db"

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS researches (
            id TEXT PRIMARY KEY,
            question_id INTEGER NOT NULL,
            data_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_research_updated ON researches(updated_at DESC)")
        conn.commit()

def count_researches() -> int:
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM researches").fetchone()
        return int(row["c"])

def save_research(research: dict[str, Any]) -> None:
    payload = json.dumps(research, ensure_ascii=False)
    with connect() as conn:
        conn.execute("""
        INSERT INTO researches(id, question_id, data_json, created_at, updated_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            question_id=excluded.question_id,
            data_json=excluded.data_json,
            updated_at=excluded.updated_at
        """, (
            research["id"],
            int(research["question"]["id"]),
            payload,
            research["created_at"],
            research["updated_at"],
        ))
        conn.commit()

def load_research(research_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT data_json FROM researches WHERE id=?", (research_id,)).fetchone()
    if not row:
        return None
    return json.loads(row["data_json"])

def list_research_rows() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT data_json FROM researches ORDER BY updated_at DESC"
        ).fetchall()
    return [json.loads(r["data_json"]) for r in rows]
