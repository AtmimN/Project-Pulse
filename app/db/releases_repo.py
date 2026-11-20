"""Repositori akses tabel releases."""
from __future__ import annotations

import sqlite3
from typing import Any


def add_release(
    conn: sqlite3.Connection,
    repo_id: int,
    release_id: int,
    tag: str,
    published_at: str,
    name: str | None = None,
    prerelease: int = 0,
) -> int:
    """Menyimpan rilis baru ke tabel releases."""
    sql = (
        "INSERT OR IGNORE INTO releases "
        "(repo_id, release_id, tag, name, published_at, prerelease) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    cursor = conn.execute(sql, (repo_id, release_id, tag, name, published_at, prerelease))
    return int(cursor.lastrowid)


def get_latest_release(conn: sqlite3.Connection, repo_id: int) -> dict[str, Any] | None:
    """Mengambil rilis terbaru (non-prerelease diutamakan) untuk suatu repositori."""
    sql = (
        "SELECT id, repo_id, release_id, tag, name, published_at, prerelease "
        "FROM releases WHERE repo_id = ? AND prerelease = 0 "
        "ORDER BY published_at DESC LIMIT 1"
    )
    row = conn.execute(sql, (repo_id,)).fetchone()
    if not row:
        # Fallback ke rilis apa pun jika belum ada non-prerelease
        sql_fallback = (
            "SELECT id, repo_id, release_id, tag, name, published_at, prerelease "
            "FROM releases WHERE repo_id = ? ORDER BY published_at DESC LIMIT 1"
        )
        row = conn.execute(sql_fallback, (repo_id,)).fetchone()
    return dict(row) if row else None
