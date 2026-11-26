"""Layanan penyedia data untuk halaman Pulse Repositori."""
from __future__ import annotations

import collections
import html
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from app import config
from app.db import comments_repo, connection, releases_repo, repos_repo
from app.sentiment.classifier import SENTIMENT_METHOD_PATH
from app.sentiment.validator import VALIDATION_JSON_PATH
from app.sentiment.preprocess import clean_text

logger = logging.getLogger(__name__)


def _extract_top_words(conn, repo_id: int, label: str, limit: int = 15) -> list[tuple[str, int]]:
    """Mengekstrak kata teratas dari komentar dengan label tertentu tanpa stopword."""
    sql = "SELECT body FROM comments WHERE repo_id = ? AND sentiment_label = ?"
    rows = conn.execute(sql, (repo_id, label)).fetchall()
    counter: collections.Counter[str] = collections.Counter()
    for r in rows:
        cleaned = clean_text(r["body"])
        tokens = re.findall(r"\b[a-zA-Z]{3,}\b", cleaned.lower())
        meaningful = [w for w in tokens if w not in ENGLISH_STOP_WORDS]
        counter.update(meaningful)
    return counter.most_common(limit)


def _get_validation_info() -> dict[str, Any]:
    """Membaca berkas evaluasi validasi sentimen dan metode aktif."""
    method_name = "VADER (Leksikon Khusus)"
    if SENTIMENT_METHOD_PATH.exists():
        try:
            with open(SENTIMENT_METHOD_PATH, "r", encoding="utf-8") as f:
                method_name = json.load(f).get("method", method_name)
        except (json.JSONDecodeError, OSError) as err:
            logger.debug("Gagal membaca konfigurasi metode sentimen: %s", err)

    validation_data = None
    if VALIDATION_JSON_PATH.exists():
        try:
            with open(VALIDATION_JSON_PATH, "r", encoding="utf-8") as f:
                validation_data = json.load(f)
        except (json.JSONDecodeError, OSError) as err:
            logger.debug("Gagal membaca berkas evaluasi validasi: %s", err)

    return {
        "method": method_name,
        "is_validated": validation_data is not None,
        "validation": validation_data,
    }


def _get_repo_stats_30d(conn: Any, rid: int) -> tuple[int, int, int, int, float]:
    """Menghitung metrik sentimen 30 hari untuk satu repositori."""
    d30_str = (datetime.now().date() - timedelta(days=29)).strftime("%Y-%m-%d")
    q30 = (
        "SELECT SUM(n_comments) as tot, SUM(n_positive) as pos, "
        "SUM(n_neutral) as neu, SUM(n_negative) as neg "
        "FROM daily_stats WHERE repo_id = ? AND stat_date >= ?"
    )
    s30 = conn.execute(q30, (rid, d30_str)).fetchone()
    tot30 = int(s30["tot"] or 0)
    pos30, neu30, neg30 = int(s30["pos"] or 0), int(s30["neu"] or 0), int(s30["neg"] or 0)
    idx30 = round((pos30 - neg30) / float(tot30), 2) if tot30 > 0 else 0.0
    return tot30, pos30, neu30, neg30, idx30


def _get_repo_monthly_trend(conn: Any, rid: int) -> list[dict[str, Any]]:
    """Menghasilkan deret tren indeks sentimen bulanan."""
    q_m = (
        "SELECT SUBSTR(stat_date, 1, 7) as month, SUM(n_comments) as tot, "
        "SUM(n_positive) as pos, SUM(n_negative) as neg FROM daily_stats "
        "WHERE repo_id = ? GROUP BY month ORDER BY month ASC"
    )
    return [
        {"month": m["month"], "index": round((m["pos"] - m["neg"]) / float(m["tot"]), 2), "comments": m["tot"]}
        for m in conn.execute(q_m, (rid,)).fetchall() if m["tot"] > 0
    ]


def _paginate_comments(conn: Any, rid: int, page: int, filter_val: str | None) -> tuple[list[dict[str, Any]], int]:
    """Mengambil halaman komentar yang ter-escape dan menghitung total halaman."""
    q_cnt = "SELECT COUNT(*) FROM comments WHERE repo_id = ?" + (" AND sentiment_label = ?" if filter_val else "")
    params = (rid, filter_val) if filter_val else (rid,)
    count_filtered = int(conn.execute(q_cnt, params).fetchone()[0])
    limit, offset = 20, max(0, (page - 1) * 20)
    comments = comments_repo.list_comments_page(conn, rid, limit, offset, filter_val)
    for c in comments:
        c["body_escaped"] = html.escape(c["body"])
    return comments, max(1, (count_filtered + 19) // 20)


def _format_pulse_response(
    monitor_repos: list[dict[str, Any]],
    selected: dict[str, Any],
    stats_30d: tuple[int, int, int, int, float],
    total_all: int,
    rel_row: Any,
    last_upd: Any,
    trend: list[dict[str, Any]],
    comments_page: tuple[list[dict[str, Any]], int],
    page: int,
    filter_val: str | None,
    top_pos: list[tuple[str, int]],
    top_neg: list[tuple[str, int]],
) -> dict[str, Any]:
    """Menyusun kamus respon akhir data pulse repositori terpilih."""
    tot30, pos30, neu30, neg30, idx30 = stats_30d
    comments, total_pages = comments_page
    return {
        "has_repos": True, "has_data": True, "repos": monitor_repos, "selected_repo": selected,
        "comments_30d": tot30, "total_stored": total_all, "index_30d": idx30,
        "pct_positive": round(pos30 / tot30 * 100, 1) if tot30 > 0 else 0.0,
        "pct_neutral": round(neu30 / tot30 * 100, 1) if tot30 > 0 else 0.0,
        "pct_negative": round(neg30 / tot30 * 100, 1) if tot30 > 0 else 0.0,
        "latest_release": dict(rel_row) if rel_row else None, "last_scraped_at": last_upd or "-",
        "max_comments": config.MAX_COMMENTS_PER_REPO, "monthly_trend": trend,
        "comments": comments, "page": page, "total_pages": total_pages,
        "filter": filter_val or "semua", "top_words_positive": top_pos,
        "top_words_negative": top_neg, "validation_info": _get_validation_info(),
    }


def get_pulse_data(
    repo_id: int | None = None,
    page: int = 1,
    sentiment_filter: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Menyusun seluruh informasi ringkasan dan detail untuk Pulse Repositori."""
    filter_val = sentiment_filter if sentiment_filter in ("positif", "netral", "negatif") else None
    with connection.transaction(db_path) as conn:
        monitor_repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
        if not monitor_repos:
            return {"has_repos": False, "repos": []}

        selected = next((r for r in monitor_repos if r["id"] == repo_id), monitor_repos[0]) if repo_id else monitor_repos[0]
        rid = selected["id"]
        total_all = comments_repo.count_comments(conn, rid)
        if total_all == 0:
            return {
                "has_repos": True, "has_data": False, "repos": monitor_repos,
                "selected_repo": selected, "validation_info": _get_validation_info(),
                "max_comments": config.MAX_COMMENTS_PER_REPO,
            }

        tot30, pos30, neu30, neg30, idx30 = _get_repo_stats_30d(conn, rid)
        rel_row = conn.execute(
            "SELECT tag, published_at FROM releases WHERE repo_id = ? ORDER BY published_at DESC LIMIT 1", (rid,)
        ).fetchone()
        last_upd = conn.execute("SELECT MAX(scraped_at) FROM comments WHERE repo_id = ?", (rid,)).fetchone()[0]

        trend = _get_repo_monthly_trend(conn, rid)
        comments, total_pages = _paginate_comments(conn, rid, page, filter_val)
        top_pos = _extract_top_words(conn, rid, "positif")
        top_neg = _extract_top_words(conn, rid, "negatif")

    return _format_pulse_response(
        monitor_repos, selected, (tot30, pos30, neu30, neg30, idx30), total_all,
        rel_row, last_upd, trend, (comments, total_pages), page, filter_val, top_pos, top_neg,
    )
