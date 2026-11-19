"""Repositori akses tabel alerts dan alert_settings."""
from __future__ import annotations

import json
import sqlite3
from typing import Any


def add_alert(
    conn: sqlite3.Connection,
    repo_id: int,
    alert_type: str,
    strength: str,
    detail: dict[str, Any],
    alert_date: str,
    dedupe_key: str,
) -> int | None:
    """Menyimpan rekaman alert baru jika dedupe_key belum pernah dicatat."""
    sql = (
        "INSERT OR IGNORE INTO alerts "
        "(repo_id, alert_type, strength, detail, alert_date, dedupe_key) "
        "VALUES (?, ?, ?, ?, ?, ?)"
    )
    cursor = conn.execute(
        sql,
        (
            repo_id,
            alert_type,
            strength,
            json.dumps(detail, ensure_ascii=False),
            alert_date,
            dedupe_key,
        ),
    )
    return int(cursor.lastrowid) if cursor.lastrowid else None


def list_recent_alerts(conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    """Mengambil riwayat alert terbaru tanpa menyertakan data sensitif pelanggan."""
    sql = (
        "SELECT a.id, a.repo_id, r.full_name as repo_name, a.alert_type, "
        "a.strength, a.detail, a.alert_date, a.created_at "
        "FROM alerts a "
        "JOIN repos r ON a.repo_id = r.id "
        "ORDER BY a.id DESC LIMIT ?"
    )
    rows = conn.execute(sql, (limit,)).fetchall()
    return [dict(r) for r in rows]
