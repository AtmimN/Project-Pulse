"""Repositori akses tabel scrape_state (watermark per aliran data)."""
from __future__ import annotations

import sqlite3
from typing import Any


def get_scrape_state(
    conn: sqlite3.Connection,
    repo_id: int,
    stream: str,
) -> dict[str, Any] | None:
    """Mengambil status watermark aliran scraping repositori."""
    sql = (
        "SELECT repo_id, stream, last_updated_at, floor_created_at, last_success_at "
        "FROM scrape_state WHERE repo_id = ? AND stream = ?"
    )
    row = conn.execute(sql, (repo_id, stream)).fetchone()
    return dict(row) if row else None


def upsert_scrape_state(
    conn: sqlite3.Connection,
    repo_id: int,
    stream: str,
    last_updated_at: str | None = None,
    floor_created_at: str | None = None,
    last_success_at: str | None = None,
) -> None:
    """Menyimpan atau memperbarui watermark dan batas lantai scraping."""
    existing = get_scrape_state(conn, repo_id, stream)
    if existing:
        new_updated = last_updated_at if last_updated_at is not None else existing.get("last_updated_at")
        new_floor = floor_created_at if floor_created_at is not None else existing.get("floor_created_at")
        new_success = last_success_at if last_success_at is not None else existing.get("last_success_at")

        sql = (
            "UPDATE scrape_state SET "
            "last_updated_at = ?, floor_created_at = ?, last_success_at = ? "
            "WHERE repo_id = ? AND stream = ?"
        )
        conn.execute(sql, (new_updated, new_floor, new_success, repo_id, stream))
    else:
        sql = (
            "INSERT INTO scrape_state "
            "(repo_id, stream, last_updated_at, floor_created_at, last_success_at) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        conn.execute(sql, (repo_id, stream, last_updated_at, floor_created_at, last_success_at))
