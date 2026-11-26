"""Repositori akses tabel repo_snapshots."""
from __future__ import annotations

import sqlite3
from typing import Any


def save_snapshot(
    conn: sqlite3.Connection,
    repo_id: int,
    as_of: str,
    n_contributors: int | None,
    n_work_items: int | None,
    kloc: float | None,
    first_commit_date: str | None = None,
    release_tag: str | None = None,
    release_date: str | None = None,
    duration_months: float | None = None,
) -> None:
    """Menyimpan atau memperbarui snapshot metrik repositori (as_of: now atau first_stable)."""
    sql = (
        "INSERT INTO repo_snapshots "
        "(repo_id, as_of, n_contributors, n_work_items, kloc, first_commit_date, "
        "release_tag, release_date, duration_months, snapshot_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP) "
        "ON CONFLICT(repo_id, as_of) DO UPDATE SET "
        "n_contributors = excluded.n_contributors, n_work_items = excluded.n_work_items, "
        "kloc = excluded.kloc, first_commit_date = excluded.first_commit_date, "
        "release_tag = excluded.release_tag, release_date = excluded.release_date, "
        "duration_months = excluded.duration_months, snapshot_at = CURRENT_TIMESTAMP"
    )
    params = (
        repo_id, as_of, n_contributors, n_work_items, kloc,
        first_commit_date, release_tag, release_date, duration_months,
    )
    conn.execute(sql, params)


def get_snapshot(conn: sqlite3.Connection, repo_id: int, as_of: str) -> dict[str, Any] | None:
    """Mengambil data snapshot repositori berdasarkan repo_id dan tipe as_of."""
    sql = "SELECT * FROM repo_snapshots WHERE repo_id = ? AND as_of = ?"
    row = conn.execute(sql, (repo_id, as_of)).fetchone()
    return dict(row) if row else None


def list_snapshots(conn: sqlite3.Connection, repo_id: int) -> list[dict[str, Any]]:
    """Mengambil daftar seluruh snapshot untuk repositori tertentu."""
    sql = "SELECT * FROM repo_snapshots WHERE repo_id = ? ORDER BY snapshot_at DESC"
    rows = conn.execute(sql, (repo_id,)).fetchall()
    return [dict(r) for r in rows]
