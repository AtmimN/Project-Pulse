"""Repositori akses tabel subscribers."""
from __future__ import annotations

import sqlite3
from typing import Any


def add_or_update_subscriber(
    conn: sqlite3.Connection,
    chat_id: int,
    sensitivity: str = "sedang",
) -> None:
    """Mendaftarkan atau mengaktifkan kembali pelanggan bot Telegram."""
    sql = (
        "INSERT INTO subscribers (chat_id, sensitivity, active) "
        "VALUES (?, ?, 1) "
        "ON CONFLICT(chat_id) DO UPDATE SET active = 1"
    )
    conn.execute(sql, (chat_id, sensitivity))


def set_sensitivity(conn: sqlite3.Connection, chat_id: int, sensitivity: str) -> None:
    """Mengubah preferensi tingkat sensitivitas alert pelanggan."""
    sql = "UPDATE subscribers SET sensitivity = ? WHERE chat_id = ?"
    conn.execute(sql, (sensitivity, chat_id))


def set_active(conn: sqlite3.Connection, chat_id: int, active: int) -> None:
    """Mengubah status aktif pelanggan."""
    sql = "UPDATE subscribers SET active = ? WHERE chat_id = ?"
    conn.execute(sql, (active, chat_id))


def get_subscriber(conn: sqlite3.Connection, chat_id: int) -> dict[str, Any] | None:
    """Mengambil data pelanggan berdasarkan chat_id."""
    sql = "SELECT chat_id, sensitivity, active, created_at FROM subscribers WHERE chat_id = ?"
    row = conn.execute(sql, (chat_id,)).fetchone()
    return dict(row) if row else None


def list_subscribers(conn: sqlite3.Connection, active_only: bool = False) -> list[dict[str, Any]]:
    """Mengambil seluruh daftar pelanggan bot."""
    sql = "SELECT chat_id, sensitivity, active, created_at FROM subscribers"
    if active_only:
        sql += " WHERE active = 1"
    sql += " ORDER BY created_at DESC"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]
