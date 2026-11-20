"""Repositori akses tabel daily_stats."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any


def upsert_daily_stats(
    conn: sqlite3.Connection,
    repo_id: int,
    stat_date: str,
    n_comments: int,
    n_positive: int,
    n_neutral: int,
    n_negative: int,
) -> None:
    """Menyimpan atau memperbarui statistik harian sentimen per repositori."""
    sql = (
        "INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(repo_id, stat_date) DO UPDATE SET "
        "n_comments = n_comments + excluded.n_comments, "
        "n_positive = n_positive + excluded.n_positive, "
        "n_neutral = n_neutral + excluded.n_neutral, "
        "n_negative = n_negative + excluded.n_negative"
    )
    conn.execute(sql, (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative))


def get_summary_stats(
    conn: sqlite3.Connection,
    repo_id: int,
    days: int = 30,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Mengambil akumulasi ringkasan sentimen untuk N hari terakhir."""
    if end_date:
        ref_dt = datetime.fromisoformat(end_date)
    else:
        ref_dt = datetime.now()

    start_date = (ref_dt - timedelta(days=days)).strftime("%Y-%m-%d")
    end_date_str = ref_dt.strftime("%Y-%m-%d")

    sql = (
        "SELECT "
        "COALESCE(SUM(n_comments), 0) AS total_comments, "
        "COALESCE(SUM(n_positive), 0) AS total_positive, "
        "COALESCE(SUM(n_neutral), 0) AS total_neutral, "
        "COALESCE(SUM(n_negative), 0) AS total_negative, "
        "MAX(stat_date) AS latest_stat_date "
        "FROM daily_stats "
        "WHERE repo_id = ? AND stat_date >= ? AND stat_date <= ?"
    )
    row = conn.execute(sql, (repo_id, start_date, end_date_str)).fetchone()
    return dict(row) if row else {
        "total_comments": 0,
        "total_positive": 0,
        "total_neutral": 0,
        "total_negative": 0,
        "latest_stat_date": None,
    }
