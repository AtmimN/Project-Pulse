"""Modul pengelola koneksi SQLite mode WAL untuk ProjectPulse."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Generator
from contextlib import contextmanager

from app import config


def get_db_path(custom_path: str | Path | None = None) -> Path:
    """Mengembalikan objek Path ke berkas database dan memastikan foldernya ada."""
    raw_path = custom_path or config.DATABASE_PATH
    path = Path(raw_path)
    if not path.is_absolute():
        path = config.BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_connection(custom_path: str | Path | None = None) -> sqlite3.Connection:
    """Membuka koneksi baru ke SQLite dengan mode WAL dan foreign keys aktif."""
    db_file = get_db_path(custom_path)
    conn = sqlite3.connect(str(db_file), timeout=10.0)
    conn.row_factory = sqlite3.Row

    # Terapkan pragma wajib sesuai spesifikasi arsitektur
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def transaction(custom_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager untuk transaksi database pendek yang aman."""
    conn = get_connection(custom_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(custom_path: str | Path | None = None) -> None:
    """Menginisialisasi skema database dari berkas schema.sql."""
    schema_file = Path(__file__).resolve().parent / "schema.sql"
    with open(schema_file, "r", encoding="utf-8") as file:
        schema_sql = file.read()

    with transaction(custom_path) as conn:
        conn.executescript(schema_sql)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(training_rows)").fetchall()]
        if cols and "repo_created_at" not in cols:
            conn.execute("ALTER TABLE training_rows ADD COLUMN repo_created_at TEXT;")
