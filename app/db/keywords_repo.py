"""Repositori akses tabel keywords dan keyword_daily."""
from __future__ import annotations

import re
import sqlite3
from typing import Any


def list_keywords(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Mengambil seluruh daftar kata kunci pemantauan."""
    sql = "SELECT id, word FROM keywords ORDER BY word ASC"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def add_keyword(conn: sqlite3.Connection, word: str) -> int:
    """Menambahkan kata kunci baru dalam huruf kecil jika belum ada."""
    cleaned = word.strip().lower()
    sql = "INSERT OR IGNORE INTO keywords (word) VALUES (?)"
    cursor = conn.execute(sql, (cleaned,))
    if cursor.lastrowid:
        return int(cursor.lastrowid)
    row = conn.execute("SELECT id FROM keywords WHERE word = ?", (cleaned,)).fetchone()
    return int(row[0]) if row else 0


def remove_keyword(conn: sqlite3.Connection, keyword_id: int) -> None:
    """Menghapus kata kunci berdasarkan ID."""
    sql = "DELETE FROM keywords WHERE id = ?"
    conn.execute(sql, (keyword_id,))


def record_keyword_hits(
    conn: sqlite3.Connection,
    repo_id: int,
    stat_date: str,
    text: str,
    keywords: list[str],
) -> dict[str, int]:
    """Mencari kemunculan kata kunci utuh pada teks dan mencatatnya ke keyword_daily."""
    hits_map: dict[str, int] = {}
    if not text or not keywords:
        return hits_map

    sql = (
        "INSERT INTO keyword_daily (repo_id, stat_date, keyword, n_hits) "
        "VALUES (?, ?, ?, ?) "
        "ON CONFLICT(repo_id, stat_date, keyword) DO UPDATE SET "
        "n_hits = n_hits + excluded.n_hits"
    )

    for kw in keywords:
        kw_clean = kw.strip().lower()
        if not kw_clean:
            continue
        pattern = rf"\b{re.escape(kw_clean)}\b"
        matches = len(re.findall(pattern, text, flags=re.IGNORECASE))
        if matches > 0:
            conn.execute(sql, (repo_id, stat_date, kw_clean, matches))
            hits_map[kw_clean] = matches

    return hits_map


def get_keyword_daily(
    conn: sqlite3.Connection,
    repo_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict[str, Any]]:
    """Mengambil rekap hitungan kata kunci harian untuk repositori."""
    sql = "SELECT repo_id, stat_date, keyword, n_hits FROM keyword_daily WHERE repo_id = ?"
    params: list[Any] = [repo_id]
    if start_date:
        sql += " AND stat_date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND stat_date <= ?"
        params.append(end_date)
    sql += " ORDER BY stat_date DESC, n_hits DESC"
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]
