"""Repositori akses tabel job_runs."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
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


def clean_stale_runs(conn: sqlite3.Connection, max_minutes: int = 30) -> int:
    """Menandai baris 'berjalan' yang lebih lama dari 30 menit sebagai gagal/macet."""
    threshold = (datetime.now() - timedelta(minutes=max_minutes)).isoformat()
    sql = (
        "UPDATE job_runs SET status = 'gagal', finished_at = ?, "
        "detail = '{\"error\": \"eksekusi macet melebihi batas waktu\"}' "
        "WHERE status = 'berjalan' AND started_at < ?"
    )
    cursor = conn.execute(sql, (datetime.now().isoformat(), threshold))
    return cursor.rowcount


def get_active_fresh_run(
    conn: sqlite3.Connection,
    job_name: str | None = None,
    max_minutes: int = 30,
) -> dict[str, Any] | None:
    """Mengambil eksekusi 'berjalan' yang masih segar (< 30 menit)."""
    clean_stale_runs(conn, max_minutes=max_minutes)
    if job_name:
        sql = "SELECT * FROM job_runs WHERE job_name = ? AND status = 'berjalan' LIMIT 1"
        row = conn.execute(sql, (job_name,)).fetchone()
    else:
        sql = "SELECT * FROM job_runs WHERE status = 'berjalan' LIMIT 1"
        row = conn.execute(sql).fetchone()
    return dict(row) if row else None


def get_last_successful_run(
    conn: sqlite3.Connection,
    job_name: str = "scrape_cycle",
) -> dict[str, Any] | None:
    """Mengambil rekaman eksekusi berhasil terakhir untuk tugas tertentu."""
    sql = "SELECT * FROM job_runs WHERE job_name = ? AND status = 'berhasil' ORDER BY id DESC LIMIT 1"
    row = conn.execute(sql, (job_name,)).fetchone()
    return dict(row) if row else None
