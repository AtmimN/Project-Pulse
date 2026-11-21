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


def get_subscribers_for_alert(
    conn: sqlite3.Connection,
    repo_id: int,
    strength: str,
) -> list[dict[str, Any]]:
    """Mengambil pelanggan aktif di watchlist repositori yang memenuhi tingkat sensitivitas."""
    if strength == "kuat":
        allowed_sens = ("rendah", "sedang", "tinggi")
    elif strength == "sedang":
        allowed_sens = ("sedang", "tinggi")
    else:
        allowed_sens = ("tinggi",)

    placeholders = ",".join("?" for _ in allowed_sens)
    sql = (
        "SELECT s.chat_id, s.sensitivity "
        "FROM subscribers s "
        "JOIN watchlist w ON s.chat_id = w.chat_id "
        f"WHERE w.repo_id = ? AND s.active = 1 AND s.sensitivity IN ({placeholders})"
    )
    params = [repo_id] + list(allowed_sens)
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def queue_alert_delivery(conn: sqlite3.Connection, alert_id: int, chat_id: int) -> None:
    """Memasukkan alert ke antrean pengiriman pesan."""
    sql = "INSERT OR IGNORE INTO alert_deliveries (alert_id, chat_id, status) VALUES (?, ?, 'menunggu')"
    conn.execute(sql, (alert_id, chat_id))


def update_delivery_status(
    conn: sqlite3.Connection,
    alert_id: int,
    chat_id: int,
    status: str,
    attempts: int = 1,
    sent_at: str | None = None,
) -> None:
    """Memperbarui status pengiriman alert (menunggu/terkirim/gagal)."""
    sql = (
        "UPDATE alert_deliveries SET status = ?, attempts = ?, sent_at = ? "
        "WHERE alert_id = ? AND chat_id = ?"
    )
    conn.execute(sql, (status, attempts, sent_at, alert_id, chat_id))


def list_pending_deliveries(conn: sqlite3.Connection, max_attempts: int = 3) -> list[dict[str, Any]]:
    """Mengambil daftar antrean pengiriman alert yang belum sukses terkirim."""
    sql = (
        "SELECT ad.alert_id, ad.chat_id, ad.attempts, a.repo_id, r.full_name as repo_name, "
        "a.alert_type, a.strength, a.detail, a.alert_date "
        "FROM alert_deliveries ad "
        "JOIN alerts a ON ad.alert_id = a.id "
        "JOIN repos r ON a.repo_id = r.id "
        "WHERE ad.status IN ('menunggu', 'gagal') AND ad.attempts < ? "
        "ORDER BY ad.alert_id ASC"
    )
    rows = conn.execute(sql, (max_attempts,)).fetchall()
    return [dict(r) for r in rows]


def is_digest_sent(conn: sqlite3.Connection, chat_id: int, digest_date: str) -> bool:
    """Memeriksa apakah ringkasan digest harian sudah pernah dikirim pada tanggal tersebut."""
    sql = "SELECT 1 FROM digest_log WHERE chat_id = ? AND digest_date = ?"
    return conn.execute(sql, (chat_id, digest_date)).fetchone() is not None


def record_digest(conn: sqlite3.Connection, chat_id: int, digest_date: str) -> bool:
    """Mencatat riwayat pengiriman digest harian ke tabel digest_log."""
    sql = "INSERT OR IGNORE INTO digest_log (chat_id, digest_date) VALUES (?, ?)"
    cursor = conn.execute(sql, (chat_id, digest_date))
    return cursor.rowcount > 0


def get_alert_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """Mengambil nilai konfigurasi alert dari tabel alert_settings."""
    sql = "SELECT value FROM alert_settings WHERE key = ?"
    row = conn.execute(sql, (key,)).fetchone()
    return str(row[0]) if row else default


def set_alert_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Menyimpan atau memperbarui nilai konfigurasi alert."""
    sql = "INSERT INTO alert_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    conn.execute(sql, (key, value))
