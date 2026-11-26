"""Layanan bisnis kartu kesehatan repositori pantau (membaca dari basis data)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
import numpy as np

from app import config
from app.db import connection, repos_repo, snapshots_repo, training_rows_repo
from app.health.rules import (
    HealthDimension,
    evaluate_mood,
    evaluate_overall,
    evaluate_speed,
    evaluate_workload,
)


def _get_training_distributions(conn: Any) -> tuple[np.ndarray, np.ndarray]:
    """Mengambil sebaran durasi dan rasio beban dari training_rows yang disertakan."""
    rows = training_rows_repo.list_training_rows(conn, included_only=True)
    durs: list[float] = []
    work_ratios: list[float] = []
    for r in rows:
        d = r.get("duration_months")
        if d is not None:
            durs.append(float(d))
        c = r.get("n_contributors")
        w = r.get("n_work_items")
        if c and w and float(c) > 0:
            work_ratios.append(float(w) / float(c))

    dur_arr = np.array(durs, dtype=float) if durs else np.array([12.0])
    work_arr = np.array(work_ratios, dtype=float) if work_ratios else np.array([5.0])
    return dur_arr, work_arr


def get_all_repos_health(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Mengambil ringkasan kartu kesehatan seluruh repositori pantau aktif."""
    with connection.transaction(db_path) as conn:
        repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)

    results: list[dict[str, Any]] = []
    for r in repos:
        health = get_repo_health_detail(r["full_name"], db_path=db_path)
        if health:
            results.append(health)
        else:
            results.append({
                "repo": r["full_name"],
                "overall_status": "abu-abu",
                "overall_reason": "Data snapshot dan aktivitas belum tersedia di sistem.",
                "has_snapshot": False,
                "dimensions": [],
            })
    return results


def get_repo_health_detail(
    repo_name: str,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Mengambil evaluasi detail kesehatan untuk satu repositori pantau."""
    with connection.transaction(db_path) as conn:
        repo = repos_repo.get_by_full_name(conn, repo_name)
        if not repo:
            return None

        repo_id = int(repo["id"])
        snap_now = snapshots_repo.get_snapshot(conn, repo_id, "now")
        snap_stable = snapshots_repo.get_snapshot(conn, repo_id, "first_stable")
        dur_arr, work_arr = _get_training_distributions(conn)

        speed_dim, speed_info = _eval_repo_speed(snap_now, snap_stable, dur_arr)
        work_dim, work_info = _eval_repo_workload(snap_now, work_arr)
        mood_dim, mood_info = _eval_repo_mood(conn, repo_id)

    dims = [speed_dim, work_dim, mood_dim]
    overall_status, overall_reason = evaluate_overall(dims)

    return {
        "repo": repo["full_name"], "repo_id": repo_id,
        "overall_status": overall_status, "overall_reason": overall_reason,
        "has_snapshot": bool(snap_now), "speed": speed_info,
        "workload": work_info, "mood": mood_info,
        "dimensions": [
            {"name": d.name, "status": d.status, "reason": d.reason, "display": d.value_display}
            for d in dims
        ],
    }


def _eval_elapsed_speed(snap_now: dict[str, Any], dur_arr: np.ndarray) -> tuple[HealthDimension, dict[str, Any]] | None:
    """Mengevaluasi kecepatan berdasarkan lama commit pertama jika snapshot stabil belum ada."""
    if not snap_now.get("first_commit_date"):
        return None
    try:
        fc_str = str(snap_now["first_commit_date"])[:10]
        fc_dt = datetime.fromisoformat(fc_str).date()
        elapsed_days = max(1, (datetime.now().date() - fc_dt).days)
        elapsed_m = round(elapsed_days / 30.4375, 1)
        pct = float(np.mean(dur_arr <= elapsed_m) * 100.0)
        dim = evaluate_speed(pct, is_elapsed=True, months_val=elapsed_m)
        return dim, {
            "status": dim.status, "reason": dim.reason, "display": dim.value_display,
            "is_elapsed": True, "months": elapsed_m, "percentile": round(pct, 1),
            "text": f"Belum ada rilis stabil; sudah berjalan {elapsed_m:.1f} bulan (persentil {pct:.0f}%).",
        }
    except (ValueError, TypeError):
        return None


def _eval_repo_speed(
    snap_now: dict[str, Any] | None,
    snap_stable: dict[str, Any] | None,
    dur_arr: np.ndarray,
) -> tuple[HealthDimension, dict[str, Any]]:
    """Kalkulasi internal dimensi kecepatan."""
    if snap_stable and snap_stable.get("duration_months") is not None:
        dur_val = float(snap_stable["duration_months"])
        pct = float(np.mean(dur_arr <= dur_val) * 100.0)
        dim = evaluate_speed(pct, is_elapsed=False, months_val=dur_val)
        return dim, {
            "status": dim.status, "reason": dim.reason, "display": dim.value_display,
            "is_elapsed": False, "months": dur_val, "percentile": round(pct, 1),
            "text": f"Rilis stabil pertama dicapai dalam {dur_val:.1f} bulan (persentil {pct:.0f}%).",
        }

    if snap_now:
        res = _eval_elapsed_speed(snap_now, dur_arr)
        if res:
            return res

    dim = evaluate_speed(None, False, None)
    return dim, {
        "status": dim.status, "reason": dim.reason, "display": dim.value_display,
        "is_elapsed": False, "months": None, "percentile": None,
        "text": "Data snapshot kecepatan belum tersedia.",
    }


def _eval_repo_workload(
    snap_now: dict[str, Any] | None,
    work_arr: np.ndarray,
) -> tuple[HealthDimension, dict[str, Any]]:
    """Kalkulasi internal dimensi beban per kontributor."""
    if snap_now and snap_now.get("n_contributors") and snap_now.get("n_work_items"):
        c = float(snap_now["n_contributors"])
        w = float(snap_now["n_work_items"])
        if c > 0:
            ratio = round(w / c, 1)
            pct = float(np.mean(work_arr <= ratio) * 100.0)
            dim = evaluate_workload(pct, tasks_per_member=ratio)
            info = {
                "status": dim.status,
                "reason": dim.reason,
                "display": dim.value_display,
                "tasks_per_member": ratio,
                "percentile": round(pct, 1),
                "n_tasks": int(w),
                "n_contributors": int(c),
            }
            return dim, info

    dim = evaluate_workload(None, None)
    return dim, {
        "status": dim.status,
        "reason": dim.reason,
        "display": dim.value_display,
        "tasks_per_member": None,
        "percentile": None,
        "n_tasks": 0,
        "n_contributors": 0,
    }


def _fetch_repo_alerts_14d(conn: Any, repo_id: int, d14_str: str) -> tuple[int, bool, bool, dict[str, int]]:
    """Mengambil riwayat alert 14 hari terakhir untuk satu repositori."""
    q_al = "SELECT alert_type, strength FROM alerts WHERE repo_id = ? AND alert_date >= ?"
    al_rows = conn.execute(q_al, (repo_id, d14_str)).fetchall()
    has_strong = any(r["strength"] == "kuat" for r in al_rows)
    has_med = any(r["strength"] == "sedang" for r in al_rows)
    counts: dict[str, int] = {}
    for r in al_rows:
        t = r["alert_type"]
        counts[t] = counts.get(t, 0) + 1
    return len(al_rows), has_strong, has_med, counts


def _eval_repo_mood(conn: Any, repo_id: int) -> tuple[HealthDimension, dict[str, Any]]:
    """Kalkulasi internal dimensi suasana (sentimen dan alert)."""
    today_dt = datetime.now().date()
    d30_str = (today_dt - timedelta(days=29)).strftime("%Y-%m-%d")
    d14_str = (today_dt - timedelta(days=13)).strftime("%Y-%m-%d")

    q_sent = (
        "SELECT SUM(n_comments) as tot, SUM(n_positive) as pos, SUM(n_negative) as neg "
        "FROM daily_stats WHERE repo_id = ? AND stat_date >= ?"
    )
    r_sent = conn.execute(q_sent, (repo_id, d30_str)).fetchone()
    tot_c = int(r_sent["tot"] or 0) if r_sent else 0
    pos_c = int(r_sent["pos"] or 0) if r_sent else 0
    neg_c = int(r_sent["neg"] or 0) if r_sent else 0
    idx_30d = round((pos_c - neg_c) / float(tot_c), 2) if tot_c > 0 else None

    al_count, has_strong, has_med, counts = _fetch_repo_alerts_14d(conn, repo_id, d14_str)
    dim = evaluate_mood(
        idx_30d, tot_c, min_comments=config.MIN_COMMENTS_FOR_SUMMARY,
        has_strong_alert_14d=has_strong, has_medium_alert_14d=has_med,
    )

    info = {
        "status": dim.status, "reason": dim.reason, "display": dim.value_display,
        "sentiment_index_30d": idx_30d, "comments_count_30d": tot_c,
        "alerts_14d_count": al_count, "has_strong_alert": has_strong,
        "has_medium_alert": has_med, "alert_breakdown": counts,
    }
    return dim, info
