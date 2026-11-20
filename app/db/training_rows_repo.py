"""Repositori akses tabel training_rows."""
from __future__ import annotations

import sqlite3
from typing import Any


def add_training_row(
    conn: sqlite3.Connection,
    repo_id: int,
    release_tag: str | None,
    release_date: str | None,
    first_commit_date: str | None,
    duration_months: float | None,
    n_contributors: int | None,
    n_work_items: int | None,
    kloc: float | None,
    included: int = 1,
    exclusion_reason: str | None = None,
    repo_created_at: str | None = None,
) -> int:
    """Menyimpan satu baris data repositori latih ke tabel training_rows."""
    sql = (
        "INSERT INTO training_rows "
        "(repo_id, release_tag, release_date, first_commit_date, repo_created_at, "
        "duration_months, n_contributors, n_work_items, kloc, included, exclusion_reason) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    cursor = conn.execute(
        sql,
        (
            repo_id,
            release_tag,
            release_date,
            first_commit_date,
            repo_created_at,
            duration_months,
            n_contributors,
            n_work_items,
            kloc,
            included,
            exclusion_reason,
        ),
    )
    return int(cursor.lastrowid)


def get_training_row_by_repo_id(conn: sqlite3.Connection, repo_id: int) -> dict[str, Any] | None:
    """Mengambil baris data latih berdasarkan repo_id."""
    sql = "SELECT * FROM training_rows WHERE repo_id = ?"
    row = conn.execute(sql, (repo_id,)).fetchone()
    return dict(row) if row else None


def list_training_rows(
    conn: sqlite3.Connection,
    included_only: bool = False,
) -> list[dict[str, Any]]:
    """Mengambil seluruh baris data latih dengan opsi hanya yang disertakan."""
    sql = (
        "SELECT tr.*, r.full_name FROM training_rows tr "
        "JOIN repos r ON tr.repo_id = r.id"
    )
    if included_only:
        sql += " WHERE tr.included = 1"
    sql += " ORDER BY tr.id ASC"
    rows = conn.execute(sql).fetchall()
    return [dict(r) for r in rows]


def delete_training_rows(conn: sqlite3.Connection) -> None:
    """Menghapus semua baris data latih (untuk opsi refresh)."""
    conn.execute("DELETE FROM training_rows")
