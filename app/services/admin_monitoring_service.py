"""Layanan pemantauan pelanggan, riwayat alert, log penjadwal, dan pengaturan alert."""
from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

from app import config
from app.alerts.tiers import DEFAULT_TIERS
from app.db import alerts_repo, connection, keywords_repo, subscribers_repo

logger = logging.getLogger(__name__)


def mask_chat_id(chat_id: int | str) -> str:
    """Menyamarkan ID chat Telegram untuk privasi (contoh: 12••••89)."""
    s = str(chat_id).strip()
    if len(s) <= 4:
        return "••••"
    return f"{s[:2]}••••{s[-2:]}"


def encode_chat_id(chat_id: int) -> str:
    """Mengenkode chat_id untuk form guna mencegah kebocoran ID asli."""
    raw = f"{chat_id}:{config.SECRET_KEY[:8]}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_chat_id(token: str) -> int:
    """Mendekode token kembali ke chat_id integer."""
    raw = base64.urlsafe_b64decode(token.encode()).decode()
    cid_str, _ = raw.split(":", 1)
    return int(cid_str)


def get_subscribers_monitoring(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil daftar pelanggan bot Telegram dengan ID tersamar dan jumlah watchlist."""
    with connection.transaction(db_path) as conn:
        subs = subscribers_repo.list_subscribers(conn)
        q_wl = "SELECT chat_id, COUNT(*) as c FROM watchlist GROUP BY chat_id"
        wl_counts = {r["chat_id"]: r["c"] for r in conn.execute(q_wl).fetchall()}

    result = []
    for s in subs:
        cid = s["chat_id"]
        result.append({
            "raw_chat_id": cid,
            "token": encode_chat_id(cid),
            "masked_chat_id": mask_chat_id(cid),
            "sensitivity": s["sensitivity"],
            "active": bool(s["active"]),
            "created_at": s.get("created_at") or "-",
            "watchlist_count": wl_counts.get(cid, 0),
        })
    return result


def _parse_detail_rows(rows: list[Any]) -> list[dict[str, Any]]:
    """Membaca baris database dan mendekode string JSON detail."""
    result = []
    for r in rows:
        d = dict(r)
        raw = d.get("detail")
        if isinstance(raw, str):
            try:
                d["detail"] = json.loads(raw)
            except (json.JSONDecodeError, TypeError) as err:
                logger.debug("Detail bukan format JSON valid: %s", err)
        result.append(d)
    return result


def get_alerts_history(
    repo_filter: str | None = None,
    type_filter: str | None = None,
    limit: int = 50,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Mengambil riwayat alert dengan filter repositori dan tipe alert."""
    sql = (
        "SELECT a.id, a.alert_type, a.strength, a.detail, a.alert_date, "
        "a.created_at, r.full_name as repo_name "
        "FROM alerts a JOIN repos r ON a.repo_id = r.id"
    )
    clauses: list[str] = []
    params: list[Any] = []
    if repo_filter:
        clauses.append("LOWER(r.full_name) = LOWER(?)")
        params.append(repo_filter.strip())
    if type_filter:
        clauses.append("a.alert_type = ?")
        params.append(type_filter.strip())

    if clauses:
        sql += f" WHERE {' AND '.join(clauses)}"
    sql += " ORDER BY a.id DESC LIMIT ?"
    params.append(limit)

    with connection.transaction(db_path) as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return _parse_detail_rows(rows)


def get_scheduler_logs(limit: int = 30, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil daftar riwayat eksekusi tugas job_runs."""
    with connection.transaction(db_path) as conn:
        sql = "SELECT * FROM job_runs ORDER BY id DESC LIMIT ?"
        rows = conn.execute(sql, (limit,)).fetchall()
    return _parse_detail_rows(rows)


def _load_tier_settings(conn: Any) -> dict[str, float]:
    """Membaca pengaturan ambang batas setiap tier alert."""
    settings: dict[str, float] = {}
    for alert_type, tiers in DEFAULT_TIERS.items():
        for tier in ("lemah", "sedang", "kuat"):
            if tier not in tiers:
                continue
            k = f"{alert_type}_{tier}"
            stored = alerts_repo.get_alert_setting(conn, k)
            settings[k] = float(stored) if stored else tiers[tier]
    return settings


def get_alert_settings_data(db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil nilai konfigurasi ambang batas alert dan daftar kata kunci."""
    with connection.transaction(db_path) as conn:
        kws = keywords_repo.list_keywords(conn)
        settings = _load_tier_settings(conn)

    return {"settings": settings, "keywords": kws}


def update_alert_setting_val(key: str, value: float, db_path: str | Path | None = None) -> None:
    """Menyimpan pembaruan nilai ambang alert ke database."""
    with connection.transaction(db_path) as conn:
        alerts_repo.set_alert_setting(conn, key, str(value))


def add_keyword_admin(word: str, db_path: str | Path | None = None) -> None:
    """Menambahkan kata kunci baru dengan validasi panjang dan karakter."""
    cleaned = word.strip().lower()
    if len(cleaned) < 2 or len(cleaned) > 30:
        raise ValueError("Kata kunci harus memiliki panjang antara 2 hingga 30 karakter.")
    with connection.transaction(db_path) as conn:
        keywords_repo.add_keyword(conn, cleaned)


def delete_keyword_admin(keyword_id: int, db_path: str | Path | None = None) -> None:
    """Menghapus kata kunci dari basis data."""
    with connection.transaction(db_path) as conn:
        keywords_repo.remove_keyword(conn, keyword_id)
