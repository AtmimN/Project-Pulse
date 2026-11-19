"""Repositori akses tabel keywords."""
from __future__ import annotations

import sqlite3
from typing import Any


def list_keywords(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Mengambil seluruh daftar kata kunci pemantauan."""
    sql = "SELECT id, word FROM keywords ORDER BY word ASC"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def add_keyword(conn: sqlite3.Connection, word: str) -> int:
    """Menambahkan kata kunci baru dalam huruf kecil."""
    cleaned = word.strip().lower()
    sql = "INSERT INTO keywords (word) VALUES (?)"
    cursor = conn.execute(sql, (cleaned,))
    return int(cursor.lastrowid)


def remove_keyword(conn: sqlite3.Connection, keyword_id: int) -> None:
    """Menghapus kata kunci berdasarkan ID."""
    sql = "DELETE FROM keywords WHERE id = ?"
    conn.execute(sql, (keyword_id,))
