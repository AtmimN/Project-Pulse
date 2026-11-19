"""Repositori akses tabel job_runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def start_job(
    conn: sqlite3.Connection,
    job_name: str,
    trigger: str,
    started_at: datetime | str | None = None,
) -> int:
    """Mencatat dimulainya eksekusi tugas ke tabel job_runs."""
    start_str = (
        started_at.isoformat()
        if isinstance(started_at, datetime)
        else (started_at or datetime.now().isoformat())
    )
    sql = (
        "INSERT INTO job_runs (job_name, trigger, started_at, status) "
        "VALUES (?, ?, ?, 'berjalan')"
    )
    cursor = conn.execute(sql, (job_name, trigger, start_str))
    return int(cursor.lastrowid)


def finish_job(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
    new_comments: int = 0,
    new_releases: int = 0,
    detail: dict[str, Any] | None = None,
    finished_at: datetime | str | None = None,
) -> None:
    """Memperbarui status akhir eksekusi tugas pada tabel job_runs."""
    finish_str = (
        finished_at.isoformat()
        if isinstance(finished_at, datetime)
        else (finished_at or datetime.now().isoformat())
    )
    detail_str = json.dumps(detail or {}, ensure_ascii=False)
    sql = (
        "UPDATE job_runs SET status = ?, finished_at = ?, new_comments = ?, "
        "new_releases = ?, detail = ? WHERE id = ?"
    )
    conn.execute(sql, (status, finish_str, new_comments, new_releases, detail_str, job_id))


def get_latest_run(conn: sqlite3.Connection, job_name: str | None = None) -> dict[str, Any] | None:
    """Mengambil rekaman eksekusi tugas terbaru."""
    if job_name:
        sql = "SELECT * FROM job_runs WHERE job_name = ? ORDER BY id DESC LIMIT 1"
        row = conn.execute(sql, (job_name,)).fetchone()
    else:
        sql = "SELECT * FROM job_runs ORDER BY id DESC LIMIT 1"
        row = conn.execute(sql).fetchone()
    return dict(row) if row else None
