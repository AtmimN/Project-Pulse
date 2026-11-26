"""Layanan bisnis Bot Telegram (watchlist, ringkasan, komparasi, sensitivitas)."""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app import config
from app.db import connection, repos_repo, subscribers_repo

_RATE_LIMITS: dict[int, list[float]] = {}


def check_rate_limit(chat_id: int, max_per_minute: int = 10) -> bool:
    """Memeriksa pembatasan laju perintah per pelanggan (maks 10 per menit)."""
    now = time.time()
    times = [t for t in _RATE_LIMITS.get(chat_id, []) if now - t < 60.0]
    if len(times) >= max_per_minute:
        return False
    times.append(now)
    _RATE_LIMITS[chat_id] = times
    return True


def reset_rate_limits() -> None:
    """Mereset catatan pembatasan laju (untuk pengujian)."""
    _RATE_LIMITS.clear()


def register_subscriber(chat_id: int, db_path: str | Path | None = None) -> None:
    """Mendaftarkan pelanggan baru atau mengaktifkan kembali pelanggan lama."""
    with connection.transaction(db_path) as conn:
        subscribers_repo.add_or_update_subscriber(conn, chat_id)


def resolve_monitor_repo(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    """Mencari repositori pantau aktif berdasarkan full_name atau nama pendek."""
    active_repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
    q = query.strip().lower()
    for r in active_repos:
        if r["full_name"].lower() == q:
            return {"status": "ok", "repo": r}

    matches = [r for r in active_repos if r["full_name"].split("/")[-1].lower() == q]
    if len(matches) == 1:
        return {"status": "ok", "repo": matches[0]}
    if len(matches) > 1:
        return {"status": "ambiguous", "matches": [r["full_name"] for r in matches]}
    return {"status": "not_found", "available": [r["full_name"] for r in active_repos]}


def add_watchlist_service(chat_id: int, repo_query: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Menambahkan repositori ke watchlist pelanggan setelah verifikasi."""
    with connection.transaction(db_path) as conn:
        resolved = resolve_monitor_repo(conn, repo_query)
        if resolved["status"] != "ok":
            return resolved
        repo = resolved["repo"]
        subscribers_repo.add_or_update_subscriber(conn, chat_id)
        added = subscribers_repo.add_to_watchlist(conn, chat_id, repo["id"])
        return {"status": "ok", "added": added, "repo": repo}


def remove_watchlist_service(chat_id: int, repo_query: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Menghapus repositori dari watchlist pelanggan."""
    with connection.transaction(db_path) as conn:
        resolved = resolve_monitor_repo(conn, repo_query)
        if resolved["status"] != "ok":
            return resolved
        repo = resolved["repo"]
        removed = subscribers_repo.remove_from_watchlist(conn, chat_id, repo["id"])
        return {"status": "ok", "removed": removed, "repo": repo}


def get_watchlist_service(chat_id: int, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil daftar repositori yang dipantau pelanggan."""
    with connection.transaction(db_path) as conn:
        return subscribers_repo.get_watchlist(conn, chat_id)


def clear_watchlist_service(chat_id: int, db_path: str | Path | None = None) -> int:
    """Mengosongkan seluruh watchlist pelanggan."""
    with connection.transaction(db_path) as conn:
        return subscribers_repo.clear_watchlist(conn, chat_id)


def get_available_repos_service(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil seluruh repositori pantau aktif."""
    with connection.transaction(db_path) as conn:
        return repos_repo.list_repos(conn, kind="monitor", active_only=True)


def _calc_repo_stats(conn: sqlite3.Connection, repo_id: int, ref_date: datetime.date) -> dict[str, Any]:
    """Menghitung metrik sentimen dan rilis untuk repositori."""
    d7_start = (ref_date - timedelta(days=6)).strftime("%Y-%m-%d")
    d30_start = (ref_date - timedelta(days=29)).strftime("%Y-%m-%d")
    prev_start = (ref_date - timedelta(days=36)).strftime("%Y-%m-%d")
    prev_end = (ref_date - timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = ref_date.strftime("%Y-%m-%d")

    q_win = "SELECT SUM(n_comments) as tot, SUM(n_positive) as pos, SUM(n_negative) as neg FROM daily_stats WHERE repo_id = ? AND stat_date BETWEEN ? AND ?"
    s7 = conn.execute(q_win, (repo_id, d7_start, today_str)).fetchone()
    sprev = conn.execute(q_win, (repo_id, prev_start, prev_end)).fetchone()

    q30 = "SELECT SUM(n_comments) as tot, SUM(n_positive) as pos, SUM(n_neutral) as neu, SUM(n_negative) as neg FROM daily_stats WHERE repo_id = ? AND stat_date BETWEEN ? AND ?"
    s30 = conn.execute(q30, (repo_id, d30_start, today_str)).fetchone()

    tot_30 = int(s30["tot"] or 0)
    pos_30 = int(s30["pos"] or 0)
    neu_30 = int(s30["neu"] or 0)
    neg_30 = int(s30["neg"] or 0)

    tot_7, pos_7, neg_7 = int(s7["tot"] or 0), int(s7["pos"] or 0), int(s7["neg"] or 0)
    tot_p, pos_p, neg_p = int(sprev["tot"] or 0), int(sprev["pos"] or 0), int(sprev["neg"] or 0)

    idx_7 = round((pos_7 - neg_7) / float(tot_7), 2) if tot_7 > 0 else 0.0
    idx_p = round((pos_p - neg_p) / float(tot_p), 2) if tot_p > 0 else 0.0
    trend = "naik" if idx_7 > idx_p + 0.02 else ("turun" if idx_7 < idx_p - 0.02 else "stabil")

    return {
        "index_7d": idx_7, "index_prev": idx_p, "trend": trend,
        "comments_7d": tot_7, "comments_30d": tot_30,
        "pct_positive": round(pos_30 / tot_30 * 100, 1) if tot_30 > 0 else 0.0,
        "pct_neutral": round(neu_30 / tot_30 * 100, 1) if tot_30 > 0 else 0.0,
        "pct_negative": round(neg_30 / tot_30 * 100, 1) if tot_30 > 0 else 0.0,
    }


def get_repo_summary_service(repo_id: int, db_path: str | Path | None = None) -> dict[str, Any]:
    """Menghitung ringkasan sentimen, komentar, dan rilis repositori."""
    with connection.transaction(db_path) as conn:
        repo = repos_repo.get_by_id(conn, repo_id)
        if not repo:
            return {"has_data": False, "repo": None}

        tot_all = conn.execute("SELECT COUNT(*) as c FROM comments WHERE repo_id = ?", (repo_id,)).fetchone()["c"]
        if tot_all == 0:
            return {"has_data": False, "repo": repo}

        stats = _calc_repo_stats(conn, repo_id, datetime.now().date())
        rel = conn.execute("SELECT tag, published_at FROM releases WHERE repo_id = ? ORDER BY published_at DESC LIMIT 1", (repo_id,)).fetchone()
        upd = conn.execute("SELECT MAX(scraped_at) as last_upd FROM comments WHERE repo_id = ?", (repo_id,)).fetchone()

        stats.update({
            "has_data": True, "repo": repo, "total_comments": tot_all,
            "latest_release": dict(rel) if rel else None,
            "last_updated": upd["last_upd"] if upd and upd["last_upd"] else None,
        })
        return stats


def _build_compare_conclusion(s1: dict[str, Any], s2: dict[str, Any], n1: str, n2: str) -> str | None:
    """Menyusun narasi kesimpulan perbandingan jika data kedua repositori mencukupi."""
    if not (s1.get("has_data") and s2.get("has_data")):
        return None
    c1, c2 = s1.get("comments_30d", 0), s2.get("comments_30d", 0)
    if c1 < config.MIN_COMMENTS_FOR_SUMMARY or c2 < config.MIN_COMMENTS_FOR_SUMMARY:
        return None
    i1, i2 = s1["index_7d"], s2["index_7d"]
    if i1 > i2:
        return f"Indeks sentimen {n1} ({i1}) lebih tinggi dibanding {n2} ({i2})."
    if i2 > i1:
        return f"Indeks sentimen {n2} ({i2}) lebih tinggi dibanding {n1} ({i1})."
    return f"Indeks sentimen {n1} dan {n2} sama kuat ({i1})."


def compare_repos_service(r1_query: str, r2_query: str, db_path: str | Path | None = None) -> dict[str, Any]:
    """Membandingkan metrik sentimen dua repositori pantau."""
    with connection.transaction(db_path) as conn:
        res1 = resolve_monitor_repo(conn, r1_query)
        if res1["status"] != "ok":
            return {"status": "error", "error_repo": r1_query, "resolution": res1}
        res2 = resolve_monitor_repo(conn, r2_query)
        if res2["status"] != "ok":
            return {"status": "error", "error_repo": r2_query, "resolution": res2}

    s1 = get_repo_summary_service(res1["repo"]["id"], db_path)
    s2 = get_repo_summary_service(res2["repo"]["id"], db_path)
    n1, n2 = res1["repo"]["full_name"], res2["repo"]["full_name"]
    conclusion = _build_compare_conclusion(s1, s2, n1, n2)

    return {"status": "ok", "repo1_summary": s1, "repo2_summary": s2, "conclusion": conclusion}


def get_or_set_sensitivity_service(chat_id: int, new_val: str | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil atau memperbarui tingkat sensitivitas alert pelanggan."""
    with connection.transaction(db_path) as conn:
        subscribers_repo.add_or_update_subscriber(conn, chat_id)
        if new_val:
            val_clean = new_val.strip().lower()
            if val_clean not in ("rendah", "sedang", "tinggi"):
                return {"status": "invalid", "valid_values": ["rendah", "sedang", "tinggi"]}
            subscribers_repo.set_sensitivity(conn, chat_id, val_clean)
            return {"status": "ok", "sensitivity": val_clean, "updated": True}

        sub = subscribers_repo.get_subscriber(conn, chat_id)
        current = sub["sensitivity"] if sub else "sedang"
        return {"status": "ok", "sensitivity": current, "updated": False}
