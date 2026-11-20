"""Repositori akses tabel issues."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def save_issue(
    conn: sqlite3.Connection,
    repo_id: int,
    number: int,
    is_pr: int,
    labels: list[str] | str,
    state: str,
    created_at: str,
    updated_at: str,
) -> None:
    """Menyimpan atau memperbarui data issue / pull request."""
    labels_str = json.dumps(labels, ensure_ascii=False) if isinstance(labels, list) else labels
    sql = (
        "INSERT INTO issues "
        "(repo_id, number, is_pr, labels, state, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(repo_id, number) DO UPDATE SET "
        "is_pr = excluded.is_pr, "
        "labels = excluded.labels, "
        "state = excluded.state, "
        "updated_at = excluded.updated_at"
    )
    conn.execute(sql, (repo_id, number, is_pr, labels_str, state, created_at, updated_at))


def get_issue(conn: sqlite3.Connection, repo_id: int, number: int) -> dict[str, Any] | None:
    """Mengambil data issue atau pull request berdasarkan nomor."""
    sql = "SELECT * FROM issues WHERE repo_id = ? AND number = ?"
    row = conn.execute(sql, (repo_id, number)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["labels"] = json.loads(data["labels"]) if data["labels"] else []
    return data
