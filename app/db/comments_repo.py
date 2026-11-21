"""Repositori akses tabel comments dan pembatasan data (pruning)."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def save_comment(
    conn: sqlite3.Connection,
    repo_id: int,
    kind: str,
    comment_id: int,
    issue_number: int,
    is_pr: int,
    labels: list[str] | str,
    body: str,
    created_at: str,
    sentiment_score: float | None = None,
    sentiment_label: str | None = None,
) -> bool:
    """Menyimpan komentar baru; mengabaikan jika (kind, comment_id) sudah ada."""
    labels_str = json.dumps(labels, ensure_ascii=False) if isinstance(labels, list) else labels
    sql = (
        "INSERT OR IGNORE INTO comments "
        "(repo_id, kind, comment_id, issue_number, is_pr, labels, body, created_at, sentiment_score, sentiment_label) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    cursor = conn.execute(
        sql,
        (
            repo_id, kind, comment_id, issue_number, is_pr,
            labels_str, body, created_at, sentiment_score, sentiment_label,
        ),
    )
    return cursor.rowcount > 0


def count_comments(conn: sqlite3.Connection, repo_id: int | None = None) -> int:
    """Menghitung total baris komentar pada suatu repositori atau seluruh database."""
    if repo_id is not None:
        sql = "SELECT COUNT(*) FROM comments WHERE repo_id = ?"
        row = conn.execute(sql, (repo_id,)).fetchone()
    else:
        sql = "SELECT COUNT(*) FROM comments"
        row = conn.execute(sql).fetchone()
    return int(row[0]) if row else 0


def prune_comments(
    conn: sqlite3.Connection,
    repo_id: int,
    max_comments: int = 2000,
) -> str | None:
    """Memangkas komentar terlama jika melebihi batas dan mengembalikan tanggal lantai baru."""
    total = count_comments(conn, repo_id)
    if total <= max_comments:
        return None

    excess_count = total - max_comments
    sql_select = (
        "SELECT id, created_at FROM comments "
        "WHERE repo_id = ? "
        "ORDER BY created_at ASC, id ASC LIMIT ?"
    )
    rows = conn.execute(sql_select, (repo_id, excess_count)).fetchall()
    if not rows:
        return None

    new_floor = str(rows[-1]["created_at"])
    ids_to_delete = [r["id"] for r in rows]
    placeholders = ",".join("?" for _ in ids_to_delete)
    conn.execute(f"DELETE FROM comments WHERE id IN ({placeholders})", ids_to_delete)
    return new_floor


def get_comments_for_export(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    """Mengambil sampel acak komentar dari database untuk ekspor pelabelan manual."""
    sql = (
        "SELECT id AS comment_id, body AS text, sentiment_label "
        "FROM comments "
        "WHERE TRIM(body) != '' "
        "ORDER BY RANDOM() LIMIT ?"
    )
    rows = conn.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]


def list_comments_page(
    conn: sqlite3.Connection,
    repo_id: int,
    limit: int = 20,
    offset: int = 0,
    sentiment_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Mengambil daftar komentar dengan paginasi dan filter sentimen."""
    sql = "SELECT * FROM comments WHERE repo_id = ?"
    params: list[Any] = [repo_id]
    if sentiment_filter in ("positif", "netral", "negatif"):
        sql += " AND sentiment_label = ?"
        params.append(sentiment_filter)
    sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(sql, tuple(params)).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        d["labels"] = json.loads(d["labels"]) if d.get("labels") else []
        results.append(d)
    return results


def update_comment_sentiment(
    conn: sqlite3.Connection,
    comment_pk: int,
    score: float,
    label: str,
) -> None:
    """Memperbarui skor dan label sentimen pada satu komentar."""
    sql = "UPDATE comments SET sentiment_score = ?, sentiment_label = ? WHERE id = ?"
    conn.execute(sql, (score, label, comment_pk))
