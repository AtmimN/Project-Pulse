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


def add_to_watchlist(conn: sqlite3.Connection, chat_id: int, repo_id: int) -> bool:
    """Menambahkan repositori ke daftar pantau pelanggan."""
    sql = "INSERT OR IGNORE INTO watchlist (chat_id, repo_id) VALUES (?, ?)"
    cursor = conn.execute(sql, (chat_id, repo_id))
    return cursor.rowcount > 0


def remove_from_watchlist(conn: sqlite3.Connection, chat_id: int, repo_id: int) -> bool:
    """Menghapus repositori dari daftar pantau pelanggan."""
    sql = "DELETE FROM watchlist WHERE chat_id = ? AND repo_id = ?"
    cursor = conn.execute(sql, (chat_id, repo_id))
    return cursor.rowcount > 0


def clear_watchlist(conn: sqlite3.Connection, chat_id: int) -> int:
    """Mengosongkan seluruh repositori dari daftar pantau pelanggan."""
    sql = "DELETE FROM watchlist WHERE chat_id = ?"
    cursor = conn.execute(sql, (chat_id,))
    return cursor.rowcount


def get_watchlist(conn: sqlite3.Connection, chat_id: int) -> list[dict[str, Any]]:
    """Mengambil repositori yang ada di watchlist pelanggan."""
    sql = (
        "SELECT r.id, r.full_name, r.kind, r.active FROM watchlist w "
        "JOIN repos r ON w.repo_id = r.id WHERE w.chat_id = ? ORDER BY r.full_name ASC"
    )
    rows = conn.execute(sql, (chat_id,)).fetchall()
    return [dict(r) for r in rows]


def is_in_watchlist(conn: sqlite3.Connection, chat_id: int, repo_id: int) -> bool:
    """Memeriksa apakah repositori ada di daftar pantau pelanggan."""
    sql = "SELECT 1 FROM watchlist WHERE chat_id = ? AND repo_id = ?"
    return conn.execute(sql, (chat_id, repo_id)).fetchone() is not None
