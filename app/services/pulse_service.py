"""Layanan penyedia data untuk halaman Pulse Repositori."""
from __future__ import annotations

import collections
import html
import json
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
        except Exception:
            pass

    validation_data = None
    if VALIDATION_JSON_PATH.exists():
        try:
            with open(VALIDATION_JSON_PATH, "r", encoding="utf-8") as f:
                validation_data = json.load(f)
        except Exception:
            pass

    return {
        "method": method_name,
        "is_validated": validation_data is not None,
        "validation": validation_data,
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

        selected = None
        if repo_id:
            for r in monitor_repos:
                if r["id"] == repo_id:
                    selected = r
                    break
        if not selected:
            selected = monitor_repos[0]

        rid = selected["id"]
        total_all = comments_repo.count_comments(conn, rid)
        if total_all == 0:
            return {
                "has_repos": True, "has_data": False, "repos": monitor_repos,
                "selected_repo": selected, "validation_info": _get_validation_info(),
                "max_comments": config.MAX_COMMENTS_PER_REPO,
            }

        # Statistik 30 Hari
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

        # Rilis terbaru & waktu scrape terakhir
        q_rel = "SELECT tag, published_at FROM releases WHERE repo_id = ? ORDER BY published_at DESC LIMIT 1"
        rel_row = conn.execute(q_rel, (rid,)).fetchone()
        q_upd = "SELECT MAX(scraped_at) FROM comments WHERE repo_id = ?"
        last_upd = conn.execute(q_upd, (rid,)).fetchone()[0]

        # Tren bulanan
        q_m = (
            "SELECT SUBSTR(stat_date, 1, 7) as month, SUM(n_comments) as tot, "
            "SUM(n_positive) as pos, SUM(n_negative) as neg FROM daily_stats "
            "WHERE repo_id = ? GROUP BY month ORDER BY month ASC"
        )
        trend = [
            {"month": m["month"], "index": round((m["pos"] - m["neg"]) / float(m["tot"]), 2), "comments": m["tot"]}
            for m in conn.execute(q_m, (rid,)).fetchall() if m["tot"] > 0
        ]

        # Paginasi komentar
        q_cnt = "SELECT COUNT(*) FROM comments WHERE repo_id = ?" + (" AND sentiment_label = ?" if filter_val else "")
        params = (rid, filter_val) if filter_val else (rid,)
        count_filtered = int(conn.execute(q_cnt, params).fetchone()[0])
        limit, offset = 20, max(0, (page - 1) * 20)
        comments = comments_repo.list_comments_page(conn, rid, limit, offset, filter_val)
        for c in comments:
            c["body_escaped"] = html.escape(c["body"])

        top_pos = _extract_top_words(conn, rid, "positif")
        top_neg = _extract_top_words(conn, rid, "negatif")

    total_pages = max(1, (count_filtered + 19) // 20)
    return {
        "has_repos": True, "has_data": True, "repos": monitor_repos,
        "selected_repo": selected, "comments_30d": tot30, "total_stored": total_all,
        "index_30d": idx30, "pct_positive": round(pos30 / tot30 * 100, 1) if tot30 > 0 else 0.0,
        "pct_neutral": round(neu30 / tot30 * 100, 1) if tot30 > 0 else 0.0,
        "pct_negative": round(neg30 / tot30 * 100, 1) if tot30 > 0 else 0.0,
        "latest_release": dict(rel_row) if rel_row else None, "last_scraped_at": last_upd or "-",
        "max_comments": config.MAX_COMMENTS_PER_REPO, "monthly_trend": trend,
        "comments": comments, "page": page, "total_pages": total_pages,
        "filter": filter_val or "semua", "top_words_positive": top_pos,
        "top_words_negative": top_neg, "validation_info": _get_validation_info(),
    }
