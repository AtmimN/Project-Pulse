"""Layanan orkestrasi siklus penuh penjadwal (snapshot, scrape, alert, digest)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app import config
from app.db import connection, job_runs_repo
from app.services.alert_service import (
    deliver_pending_alerts,
    evaluate_and_save_alerts,
    send_daily_digest,
)
from app.services.scrape_service import scrape_all_monitor_repos
from app.services.snapshot_service import snapshot_all_monitor_repos

try:
    APP_TZ = ZoneInfo(config.TIMEZONE)
except Exception:
    APP_TZ = timezone.utc


def should_run_susulan(
    now: datetime | None = None,
    db_path: str | Path | None = None,
) -> bool:
    """Memeriksa apakah perlu menjalankan siklus susulan (> 24 jam sejak sukses terakhir)."""
    ref_now = now or datetime.now(APP_TZ)
    with connection.transaction(db_path) as conn:
        last = job_runs_repo.get_last_successful_run(conn, "scrape_cycle")
        if not last:
            return True

        fin_str = last.get("finished_at") or last.get("started_at")
        if not fin_str:
            return True
        try:
            fin_dt = datetime.fromisoformat(fin_str.replace("Z", "+00:00"))
            if fin_dt.tzinfo is None:
                fin_dt = fin_dt.replace(tzinfo=APP_TZ)
            diff_hours = (ref_now - fin_dt).total_seconds() / 3600.0
            return diff_hours >= 24.0
        except Exception:
            return True


def run_cycle(
    trigger: str = "terjadwal",
    now: datetime | None = None,
    db_path: str | Path | None = None,
    notifier: Any = None,
    github_client: Any = None,
) -> dict[str, Any]:
    """Menjalankan satu siklus penuh: snapshot, scrape, alert, delivery, dan digest."""
    ref_now = now or datetime.now(APP_TZ)
    today_str = ref_now.strftime("%Y-%m-%d")

    with connection.transaction(db_path) as conn:
        active = job_runs_repo.get_active_fresh_run(conn, "scrape_cycle")
        if active:
            raise RuntimeError("Eksekusi siklus scrape_cycle sedang berjalan.")
        job_id = job_runs_repo.start_job(conn, "scrape_cycle", trigger, started_at=ref_now)

    tot_comments = 0
    tot_releases = 0
    detail: dict[str, Any] = {"trigger": trigger, "target_date": today_str}

    try:
        # 1. Scraping incremental
        scrape_res = scrape_all_monitor_repos(github_client=github_client, db_path=db_path, trigger=trigger)
        tot_comments = scrape_res.get("new_comments", 0)
        tot_releases = scrape_res.get("new_releases", 0)
        detail["scraping"] = scrape_res.get("results", [])

        # 2. Evaluasi alert
        alerts_list = evaluate_and_save_alerts(alert_date=today_str, db_path=db_path)
        detail["alerts_generated"] = len(alerts_list)

        # 3. Pengiriman alert
        deliv_res = deliver_pending_alerts(notifier=notifier, db_path=db_path)
        detail["delivery"] = deliv_res

        # 4. Pengiriman digest harian
        dig_count = send_daily_digest(digest_date=today_str, notifier=notifier, db_path=db_path)
        detail["digests_sent"] = dig_count

        final_status = scrape_res.get("status", "berhasil")
    except Exception as err:
        final_status = "gagal"
        detail["error"] = str(err)

    with connection.transaction(db_path) as conn:
        job_runs_repo.finish_job(
            conn, job_id, final_status, tot_comments, tot_releases, detail, finished_at=datetime.now(APP_TZ)
        )

    return {
        "job_id": job_id,
        "status": final_status,
        "new_comments": tot_comments,
        "new_releases": tot_releases,
        "detail": detail,
    }
