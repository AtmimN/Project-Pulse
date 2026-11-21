"""Titik masuk eksekusi Penjadwal Scraping & Alert: python -m app.scheduler."""
from __future__ import annotations

import argparse
from datetime import timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app import config
from app.services.cycle_service import run_cycle, should_run_susulan

try:
    APP_TZ = ZoneInfo(config.TIMEZONE)
except Exception:
    APP_TZ = timezone.utc


def setup_scheduler() -> BlockingScheduler:
    """Mengonfigurasi penjadwal APScheduler dengan pekerjaan harian."""
    sched = BlockingScheduler(timezone=APP_TZ)
    sched.add_job(
        run_cycle,
        trigger="cron",
        hour=config.SCRAPE_HOUR,
        minute=config.SCRAPE_MINUTE,
        args=["terjadwal"],
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return sched


def run_scheduler_main(args: list[str] | None = None) -> None:
    """Menjalankan loop utama penjadwal atau eksekusi tunggal (--once)."""
    parser = argparse.ArgumentParser(description="Penjadwal Siklus Harian ProjectPulse")
    parser.add_argument("--once", action="store_true", help="Jalankan satu siklus penuh lalu keluar")
    parsed = parser.parse_args(args)

    if parsed.once:
        print("Menjalankan satu siklus penjadwal (--once)...")
        res = run_cycle(trigger="manual")
        print(f"Siklus selesai. Status: {res.get('status')}")
        return

    print("Memulai proses penjadwal ProjectPulse...")
    if should_run_susulan():
        print("Siklus berhasil terakhir > 24 jam lalu. Menjalankan siklus susulan...")
        try:
            res_susulan = run_cycle(trigger="susulan")
            print(f"Siklus susulan selesai. Status: {res_susulan.get('status')}")
        except Exception as e:
            print(f"Gagal menjalankan siklus susulan: {e}")

    sched = setup_scheduler()
    print(
        f"Penjadwal aktif. Pekerjaan terjadwal pada {config.SCRAPE_HOUR:02d}:{config.SCRAPE_MINUTE:02d} ({config.TIMEZONE})."
    )
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        print("Penjadwal dihentikan.")


if __name__ == "__main__":
    run_scheduler_main()
