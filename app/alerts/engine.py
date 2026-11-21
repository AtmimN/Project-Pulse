"""Mesin evaluasi aturan alert kesehatan proyek berbasis data ringkasan (modul murni)."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.alerts.tiers import DEFAULT_TIERS, determine_strength


def _filter_stats_by_date(stats: list[dict[str, Any]], start_date: str, end_date: str) -> list[dict[str, Any]]:
    """Menyaring baris daily_stats dalam rentang tanggal inklusif."""
    return [r for r in stats if start_date <= str(r.get("stat_date", "")) <= end_date]


def _calc_window_stats(stats: list[dict[str, Any]]) -> tuple[int, int, int]:
    """Menghitung total komentar, positif, dan negatif dari daftar baris daily_stats."""
    tot = sum(int(r.get("n_comments", 0)) for r in stats)
    pos = sum(int(r.get("n_positive", 0)) for r in stats)
    neg = sum(int(r.get("n_negative", 0)) for r in stats)
    return tot, pos, neg


def check_sentimen_turun(
    daily_stats: list[dict[str, Any]],
    alert_date: str,
    repo_id: int,
    tiers: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Mengevaluasi penurunan indeks sentimen 7 hari terakhir vs 30 hari sebelumnya."""
    cfg = tiers or DEFAULT_TIERS["sentimen_turun"]
    ref_dt = datetime.fromisoformat(alert_date)

    d7_start = (ref_dt - timedelta(days=6)).strftime("%Y-%m-%d")
    tot_7, pos_7, neg_7 = _calc_window_stats(_filter_stats_by_date(daily_stats, d7_start, alert_date))

    d30_start = (ref_dt - timedelta(days=36)).strftime("%Y-%m-%d")
    d30_end = (ref_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    tot_30, pos_30, neg_30 = _calc_window_stats(_filter_stats_by_date(daily_stats, d30_start, d30_end))

    if tot_7 < cfg["min_comments"] or tot_30 < cfg["min_comments"]:
        return None

    idx_7 = (pos_7 - neg_7) / float(tot_7)
    idx_30 = (pos_30 - neg_30) / float(tot_30)
    drop = round(idx_30 - idx_7, 4)

    strength = determine_strength(drop, cfg["lemah"], cfg["sedang"], cfg["kuat"])
    if not strength:
        return None

    return {
        "repo_id": repo_id, "alert_type": "sentimen_turun", "strength": strength,
        "alert_date": alert_date, "dedupe_key": f"sentimen_turun:{repo_id}:{alert_date}",
        "detail": {
            "drop": drop, "index_7d": round(idx_7, 4), "index_30d_prev": round(idx_30, 4),
            "comments_7d": tot_7, "comments_30d": tot_30,
        },
    }


def check_lonjakan_negatif(
    daily_stats: list[dict[str, Any]],
    alert_date: str,
    repo_id: int,
    tiers: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Mengevaluasi lonjakan komentar negatif hari ini vs rata-rata 30 hari sebelumnya."""
    cfg = tiers or DEFAULT_TIERS["lonjakan_negatif"]
    ref_dt = datetime.fromisoformat(alert_date)

    today_stats = [r for r in daily_stats if str(r.get("stat_date", "")) == alert_date]
    neg_today = sum(int(r.get("n_negative", 0)) for r in today_stats)
    if neg_today < cfg["min_negative"]:
        return None

    d30_start = (ref_dt - timedelta(days=30)).strftime("%Y-%m-%d")
    d30_end = (ref_dt - timedelta(days=1)).strftime("%Y-%m-%d")
    _, _, neg_prev = _calc_window_stats(_filter_stats_by_date(daily_stats, d30_start, d30_end))

    avg_neg_daily = neg_prev / 30.0
    ratio = (neg_today / avg_neg_daily) if avg_neg_daily > 0 else float(neg_today)
    strength = determine_strength(ratio, cfg["lemah"], cfg["sedang"], cfg["kuat"])
    if not strength:
        return None

    return {
        "repo_id": repo_id, "alert_type": "lonjakan_negatif", "strength": strength,
        "alert_date": alert_date, "dedupe_key": f"lonjakan_negatif:{repo_id}:{alert_date}",
        "detail": {"neg_today": neg_today, "avg_prev_30d": round(avg_neg_daily, 2), "ratio": round(ratio, 2)},
    }


def check_rilis_bermasalah(
    daily_stats: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    alert_date: str,
    repo_id: int,
    tiers: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Mengevaluasi apakah rilis terbaru (maks 3 hari) memicu kenaikan proporsi komentar negatif."""
    cfg = tiers or DEFAULT_TIERS["rilis_bermasalah"]
    ref_dt = datetime.fromisoformat(alert_date)
    candidates: list[dict[str, Any]] = []

    for rel in releases:
        if rel.get("is_draft") or rel.get("draft"):
            continue
        pub_str = str(rel.get("published_at", ""))[:10]
        if not pub_str:
            continue
        try:
            rel_dt = datetime.fromisoformat(pub_str)
        except Exception:
            continue
        if not (0 <= (ref_dt - rel_dt).days <= cfg.get("days_window", 3)):
            continue

        tot_post, _, neg_post = _calc_window_stats(_filter_stats_by_date(daily_stats, pub_str, alert_date))
        if tot_post < cfg["min_comments"]:
            continue

        pre_start = (rel_dt - timedelta(days=30)).strftime("%Y-%m-%d")
        pre_end = (rel_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        tot_pre, _, neg_pre = _calc_window_stats(_filter_stats_by_date(daily_stats, pre_start, pre_end))

        prop_post = neg_post / float(tot_post)
        prop_pre = (neg_pre / float(tot_pre)) if tot_pre > 0 else 0.0
        diff = round(prop_post - prop_pre, 4)
        strength = determine_strength(diff, cfg["lemah"], cfg["sedang"], cfg["kuat"])
        if strength:
            tag = str(rel.get("tag", ""))
            candidates.append({
                "repo_id": repo_id, "alert_type": "rilis_bermasalah", "strength": strength,
                "alert_date": alert_date, "dedupe_key": f"rilis_bermasalah:{repo_id}:{alert_date}:{tag}",
                "detail": {
                    "tag": tag, "diff": diff, "prop_post": round(prop_post, 4),
                    "prop_pre": round(prop_pre, 4), "comments_post": tot_post,
                },
            })
    return candidates


def check_kata_kunci(
    keyword_daily: list[dict[str, Any]],
    alert_date: str,
    repo_id: int,
    tiers: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Mengevaluasi kemunculan kata kunci kritis pada tanggal alert."""
    cfg = tiers or DEFAULT_TIERS["kata_kunci"]
    candidates: list[dict[str, Any]] = []

    today_hits = [r for r in keyword_daily if str(r.get("stat_date", "")) == alert_date]
    for row in today_hits:
        hits = int(row.get("n_hits", 0))
        kw = str(row.get("keyword", "")).strip().lower()
        strength = determine_strength(hits, cfg["lemah"], cfg["sedang"], cfg["kuat"])
        if strength:
            candidates.append({
                "repo_id": repo_id, "alert_type": "kata_kunci", "strength": strength,
                "alert_date": alert_date, "dedupe_key": f"kata_kunci:{repo_id}:{alert_date}:{kw}",
                "detail": {"keyword": kw, "hits": hits},
            })
    return candidates


def evaluate_all_rules(
    repo_id: int,
    daily_stats: list[dict[str, Any]],
    keyword_daily: list[dict[str, Any]],
    releases: list[dict[str, Any]],
    alert_date: str,
    custom_tiers: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Mengevaluasi seluruh 4 jenis aturan alert untuk satu repositori pada tanggal tertentu."""
    tiers_map = custom_tiers or DEFAULT_TIERS
    alerts: list[dict[str, Any]] = []

    a1 = check_sentimen_turun(daily_stats, alert_date, repo_id, tiers_map.get("sentimen_turun"))
    if a1:
        alerts.append(a1)
    a2 = check_lonjakan_negatif(daily_stats, alert_date, repo_id, tiers_map.get("lonjakan_negatif"))
    if a2:
        alerts.append(a2)

    alerts.extend(check_rilis_bermasalah(daily_stats, releases, alert_date, repo_id, tiers_map.get("rilis_bermasalah")))
    alerts.extend(check_kata_kunci(keyword_daily, alert_date, repo_id, tiers_map.get("kata_kunci")))
    return alerts
