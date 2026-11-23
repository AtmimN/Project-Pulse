"""Layanan pembaca data analitik dan metrik regresi untuk dashboard."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app import config
from app.db import alerts_repo, connection, estimations_repo, repos_repo, training_rows_repo
from app.estimator.model_a import METRICS_A_PATH
from app.estimator.model_b import METRICS_B_PATH


def get_regression_a_data(db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Mengambil metrik dan diagnostik Model A beserta jumlah data latih."""
    if not METRICS_A_PATH.exists():
        return None
    try:
        with open(METRICS_A_PATH, "r", encoding="utf-8") as f:
            metrics = json.load(f)
    except Exception:
        return None

    try:
        with connection.transaction(db_path) as conn:
            n_rows = len(training_rows_repo.list_training_rows(conn, included_only=True))
    except Exception:
        n_rows = metrics.get("n_train", 0) + metrics.get("n_test", 0)

    metrics["n_training_rows"] = n_rows
    metrics["warning_insufficient"] = n_rows < config.MIN_TRAINING_ROWS

    if "typical_duration" not in metrics:
        try:
            with connection.transaction(db_path) as conn:
                rows = training_rows_repo.list_training_rows(conn, included_only=True)
                durs = sorted([float(r["duration_months"]) for r in rows if r["duration_months"] is not None])
                if durs:
                    import numpy as np
                    q25 = round(float(np.percentile(durs, 25)), 2)
                    q75 = round(float(np.percentile(durs, 75)), 2)
                    metrics["typical_duration"] = {
                        "median": round(float(np.median(durs)), 2),
                        "q25": q25,
                        "q75": q75,
                        "iqr": round(float(q75 - q25), 2),
                    }
        except Exception:
            pass

    return metrics


def get_duration_benchmark(db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil metrik benchmark durasi dari berkas JSON atau basis data."""
    from app.estimator.benchmark import calculate_duration_benchmark, load_duration_benchmark
    bench = load_duration_benchmark()
    if bench and bench.get("n", 0) > 0:
        return bench
    try:
        with connection.transaction(db_path) as conn:
            rows = training_rows_repo.list_training_rows(conn, included_only=True)
            durs = [float(r["duration_months"]) for r in rows if r.get("duration_months") is not None]
            return calculate_duration_benchmark(durs)
    except Exception:
        return calculate_duration_benchmark([])


def get_regression_b_data() -> dict[str, Any] | None:
    """Mengambil metrik dan pasangan aktual-prediksi Model B NASA93."""
    if not METRICS_B_PATH.exists():
        return None
    try:
        with open(METRICS_B_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_dashboard_summary(db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil ringkasan metrik utama untuk panel ringkasan dashboard."""
    d30_str = (datetime.now().date() - timedelta(days=29)).strftime("%Y-%m-%d")
    with connection.transaction(db_path) as conn:
        r_30 = conn.execute("SELECT SUM(n_comments) as tot FROM daily_stats WHERE stat_date >= ?", (d30_str,)).fetchone()
        tot_comments = int(r_30["tot"] or 0) if r_30 else 0
        repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
        q_top = (
            "SELECT r.full_name, SUM(d.n_comments) as tot, SUM(d.n_positive) as pos, SUM(d.n_negative) as neg "
            "FROM daily_stats d JOIN repos r ON d.repo_id = r.id "
            "WHERE d.stat_date >= ? GROUP BY d.repo_id HAVING tot >= 1"
        )
        stats_rows = conn.execute(q_top, (d30_str,)).fetchall()
        top_repo = None
        best_idx = -2.0
        for sr in stats_rows:
            tot = sr["tot"]
            idx = round((sr["pos"] - sr["neg"]) / float(tot), 2)
            if idx > best_idx:
                best_idx = idx
                top_repo = {"name": sr["full_name"], "index": idx, "comments": tot}
        est_count = int(conn.execute("SELECT COUNT(*) FROM estimations").fetchone()[0])
        last_scraped = conn.execute("SELECT MAX(scraped_at) FROM comments").fetchone()[0]

    return {
        "comments_30d": tot_comments,
        "monitor_repos_count": len(repos),
        "top_sentiment_repo": top_repo,
        "estimations_count": est_count,
        "last_scraped_at": last_scraped or "-",
    }


def get_sentiment_by_repo(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil komposisi sentimen 30 hari per repositori untuk grafik bar."""
    d30_str = (datetime.now().date() - timedelta(days=29)).strftime("%Y-%m-%d")
    with connection.transaction(db_path) as conn:
        q = (
            "SELECT r.full_name, COALESCE(SUM(d.n_positive), 0) as pos, "
            "COALESCE(SUM(d.n_neutral), 0) as neu, COALESCE(SUM(d.n_negative), 0) as neg, "
            "COALESCE(SUM(d.n_comments), 0) as tot FROM repos r "
            "LEFT JOIN daily_stats d ON r.id = d.repo_id AND d.stat_date >= ? "
            "WHERE r.kind = 'monitor' AND r.active = 1 GROUP BY r.id ORDER BY r.full_name ASC"
        )
        rows = conn.execute(q, (d30_str,)).fetchall()

    result = []
    for r in rows:
        tot = int(r["tot"])
        pos, neu, neg = int(r["pos"]), int(r["neu"]), int(r["neg"])
        result.append({
            "repo": r["full_name"], "total": tot,
            "positive": pos, "neutral": neu, "negative": neg,
            "pct_positive": round(pos / tot * 100, 1) if tot > 0 else 0.0,
            "pct_neutral": round(neu / tot * 100, 1) if tot > 0 else 0.0,
            "pct_negative": round(neg / tot * 100, 1) if tot > 0 else 0.0,
        })
    return result


def get_sentiment_trend(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil tren indeks sentimen bulanan per repositori untuk grafik garis."""
    with connection.transaction(db_path) as conn:
        q = (
            "SELECT r.full_name, SUBSTR(d.stat_date, 1, 7) as month, "
            "SUM(d.n_comments) as tot, SUM(d.n_positive) as pos, SUM(d.n_negative) as neg "
            "FROM daily_stats d JOIN repos r ON d.repo_id = r.id "
            "WHERE r.kind = 'monitor' AND r.active = 1 "
            "GROUP BY r.id, month ORDER BY month ASC, r.full_name ASC"
        )
        rows = conn.execute(q).fetchall()

    repos_data: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        fn, tot = r["full_name"], int(r["tot"])
        idx = round((r["pos"] - r["neg"]) / float(tot), 2) if tot > 0 else 0.0
        repos_data.setdefault(fn, []).append({"month": r["month"], "index": idx, "comments": tot})
    return [{"repo": fn, "points": pts} for fn, pts in repos_data.items()]


def get_training_data_summary(db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil statistik data latih (disertakan/dikeluarkan & sebaran durasi)."""
    with connection.transaction(db_path) as conn:
        rows = conn.execute("SELECT included, exclusion_reason, duration_months FROM training_rows").fetchall()

    inc = [r for r in rows if r["included"] == 1]
    exc = [r for r in rows if r["included"] == 0]
    reasons: dict[str, int] = {}
    for r in exc:
        k = r["exclusion_reason"] or "Tidak diketahui"
        reasons[k] = reasons.get(k, 0) + 1

    durations = sorted([float(r["duration_months"]) for r in inc if r["duration_months"] is not None])
    dur_stats = {
        "min": round(durations[0], 1) if durations else 0,
        "max": round(durations[-1], 1) if durations else 0,
        "median": round(durations[len(durations) // 2], 1) if durations else 0,
        "count": len(durations),
    }
    return {
        "total": len(rows), "included_count": len(inc),
        "excluded_count": len(exc), "exclusion_reasons": reasons,
        "duration_distribution": dur_stats,
    }


def get_recent_estimations(limit: int = 5, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil daftar estimasi terbaru."""
    with connection.transaction(db_path) as conn:
        return estimations_repo.list_recent_estimations(conn, limit=limit)


def get_recent_alerts(limit: int = 10, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil riwayat alert terbaru tanpa identitas pengguna."""
    with connection.transaction(db_path) as conn:
        rows = alerts_repo.list_recent_alerts(conn, limit=limit)
    for r in rows:
        if isinstance(r.get("detail"), str):
            try:
                r["detail"] = json.loads(r["detail"])
            except Exception:
                pass
    return rows


def get_scheduler_status(db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil status eksekusi penjadwal harian terakhir."""
    with connection.transaction(db_path) as conn:
        row = conn.execute("SELECT * FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()

    schedule_str = f"{config.SCRAPE_HOUR:02d}:{config.SCRAPE_MINUTE:02d} {config.TIMEZONE}"
    if not row:
        return {"has_run": False, "schedule": schedule_str, "last_run": None}

    d = dict(row)
    if isinstance(d.get("detail"), str):
        try:
            d["detail"] = json.loads(d["detail"])
        except Exception:
            pass
    return {"has_run": True, "schedule": schedule_str, "last_run": d}
