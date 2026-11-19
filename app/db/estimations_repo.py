"""Repositori akses tabel estimations."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def save_estimation(
    conn: sqlite3.Connection,
    input_payload: dict[str, Any],
    result_payload: dict[str, Any],
) -> int:
    """Menyimpan hasil kalkulasi estimasi ke basis data."""
    sql = "INSERT INTO estimations (input_payload, result_payload) VALUES (?, ?)"
    cursor = conn.execute(
        sql,
        (
            json.dumps(input_payload, ensure_ascii=False),
            json.dumps(result_payload, ensure_ascii=False),
        ),
    )
    return int(cursor.lastrowid)


def list_recent_estimations(conn: sqlite3.Connection, limit: int = 5) -> list[dict[str, Any]]:
    """Mengambil riwayat estimasi terbaru."""
    sql = "SELECT id, input_payload, result_payload, created_at FROM estimations ORDER BY id DESC LIMIT ?"
    rows = conn.execute(sql, (limit,)).fetchall()
    results: list[dict[str, Any]] = []
    for r in rows:
        results.append(
            {
                "id": r["id"],
                "input": json.loads(r["input_payload"]),
                "result": json.loads(r["result_payload"]),
                "created_at": r["created_at"],
            }
        )
    return results
