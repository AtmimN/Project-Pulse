"""Repositori akses tabel repos."""
from __future__ import annotations

import sqlite3
from typing import Any


def add_repo(
    conn: sqlite3.Connection,
    full_name: str,
    kind: str,
    active: int = 1,
) -> int:
    """Menambahkan repositori baru dan mengembalikan ID baris yang dibuat."""
    sql = "INSERT INTO repos (full_name, kind, active) VALUES (?, ?, ?)"
    cursor = conn.execute(sql, (full_name.strip(), kind, active))
    return int(cursor.lastrowid)


def get_by_id(conn: sqlite3.Connection, repo_id: int) -> dict[str, Any] | None:
    """Mengambil data repositori berdasarkan ID uniknya."""
    sql = "SELECT id, full_name, kind, active, added_at FROM repos WHERE id = ?"
    row = conn.execute(sql, (repo_id,)).fetchone()
    return dict(row) if row else None


def get_by_full_name(conn: sqlite3.Connection, full_name: str) -> dict[str, Any] | None:
    """Mengambil data repositori berdasarkan full_name secara case-insensitive."""
    sql = "SELECT id, full_name, kind, active, added_at FROM repos WHERE LOWER(full_name) = LOWER(?)"
    row = conn.execute(sql, (full_name.strip(),)).fetchone()
    return dict(row) if row else None


def list_repos(
    conn: sqlite3.Connection,
    kind: str | None = None,
    active_only: bool = False,
) -> list[dict[str, Any]]:
    """Mengambil daftar repositori dengan filter jenis dan status aktif."""
    clauses: list[str] = []
    params: list[Any] = []

    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if active_only:
        clauses.append("active = 1")

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT id, full_name, kind, active, added_at FROM repos {where} ORDER BY id ASC"
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def set_active(conn: sqlite3.Connection, repo_id: int, active: int) -> None:
    """Mengubah status aktif/nonaktif sebuah repositori."""
    sql = "UPDATE repos SET active = ? WHERE id = ?"
    conn.execute(sql, (active, repo_id))


def ensure_monitor_repos_loaded(conn: sqlite3.Connection, json_path: Any = None) -> list[dict[str, Any]]:
    """Memastikan repositori pantau awal dari monitor_repos.json tercatat di tabel repos."""
    import json
    from pathlib import Path
    from app import config

    target = Path(json_path) if json_path else (config.BASE_DIR / "data" / "monitor_repos.json")
    if not target.exists():
        return list_repos(conn, kind="monitor", active_only=True)

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        for r in data.get("repos", []):
            fn = r.get("full_name", "").strip()
            if fn and not get_by_full_name(conn, fn):
                add_repo(conn, fn, kind="monitor", active=1)
    except (json.JSONDecodeError, OSError, KeyError) as err:
        import logging
        logging.getLogger(__name__).warning("Gagal memuat repositori pantau awal: %s", err)
    return list_repos(conn, kind="monitor", active_only=True)
