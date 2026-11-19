"""Repositori akses tabel conversation_logs."""
from __future__ import annotations

import sqlite3
from typing import Any


def log_conversation(
    conn: sqlite3.Connection,
    session_id: str,
    message: str,
    reply: str,
    intent: str | None = None,
) -> int:
    """Mencatat interaksi percakapan baru ke basis data."""
    sql = (
        "INSERT INTO conversation_logs (session_id, message, intent, reply) "
        "VALUES (?, ?, ?, ?)"
    )
    cursor = conn.execute(sql, (session_id, message, intent, reply))
    return int(cursor.lastrowid)


def list_conversations(
    conn: sqlite3.Connection,
    limit: int = 20,
    offset: int = 0,
    intent_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Mengambil daftar riwayat percakapan untuk tampilan admin."""
    if intent_filter:
        sql = (
            "SELECT id, session_id, message, intent, reply, created_at "
            "FROM conversation_logs WHERE intent = ? "
            "ORDER BY id DESC LIMIT ? OFFSET ?"
        )
        rows = conn.execute(sql, (intent_filter, limit, offset)).fetchall()
    else:
        sql = (
            "SELECT id, session_id, message, intent, reply, created_at "
            "FROM conversation_logs ORDER BY id DESC LIMIT ? OFFSET ?"
        )
        rows = conn.execute(sql, (limit, offset)).fetchall()
    return [dict(r) for r in rows]
