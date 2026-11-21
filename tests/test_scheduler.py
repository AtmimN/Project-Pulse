"""Pengujian penjadwal siklus (APScheduler, susulan, job_runs, digest, mode --once)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from zoneinfo import ZoneInfo

from app.db import connection, job_runs_repo, repos_repo, subscribers_repo
from app.scheduler.__main__ import run_scheduler_main
from app.services.alert_service import send_daily_digest
from app.services.cycle_service import run_cycle, should_run_susulan


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Membuat database sementara dengan skema lengkap."""
    db_file = tmp_path / "test_scheduler.db"
    conn = sqlite3.connect(db_file)
    schema_sql = (Path(__file__).resolve().parent.parent / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.close()
    return db_file


def test_should_run_susulan_logic(test_db: Path) -> None:
    """Menguji evaluasi kebutuhan siklus susulan (> 24 jam sejak eksekusi sukses terakhir)."""
    tz = ZoneInfo("Asia/Jakarta")
    now_dt = datetime(2026, 5, 10, 10, 0, 0, tzinfo=tz)

    # 1. Belum pernah ada eksekusi sukses -> True
    assert should_run_susulan(now=now_dt, db_path=test_db) is True

    # 2. Eksekusi sukses 25 jam yang lalu -> True
    old_dt = now_dt - timedelta(hours=25)
    with connection.transaction(test_db) as conn:
        jid = job_runs_repo.start_job(conn, "scrape_cycle", "terjadwal", started_at=old_dt)
        job_runs_repo.finish_job(conn, jid, "berhasil", finished_at=old_dt)

    assert should_run_susulan(now=now_dt, db_path=test_db) is True

    # 3. Eksekusi sukses 2 jam yang lalu -> False
    recent_dt = now_dt - timedelta(hours=2)
    with connection.transaction(test_db) as conn:
        jid2 = job_runs_repo.start_job(conn, "scrape_cycle", "terjadwal", started_at=recent_dt)
        job_runs_repo.finish_job(conn, jid2, "berhasil", finished_at=recent_dt)

    assert should_run_susulan(now=now_dt, db_path=test_db) is False


def test_job_runs_lifecycle_and_stale_cleanup(test_db: Path) -> None:
    """Menguji siklus hidup job_runs dan pembersihan baris macet (> 30 menit)."""
    # 1. Catat job baru
    with connection.transaction(test_db) as conn:
        jid = job_runs_repo.start_job(conn, "scrape_cycle", "manual")
        run = job_runs_repo.get_latest_run(conn, "scrape_cycle")
        assert run is not None
        assert run["status"] == "berjalan"

        # Selesaikan job
        job_runs_repo.finish_job(conn, jid, "berhasil", new_comments=5, new_releases=1, detail={"info": "ok"})
        run_finished = job_runs_repo.get_latest_run(conn, "scrape_cycle")
        assert run_finished is not None
        assert run_finished["status"] == "berhasil"
        assert run_finished["new_comments"] == 5

    # 2. Job macet (> 30 menit)
    stale_time = (datetime.now() - timedelta(minutes=45)).isoformat()
    with connection.transaction(test_db) as conn:
        conn.execute(
            "INSERT INTO job_runs (job_name, trigger, started_at, status) VALUES ('scrape_cycle', 'terjadwal', ?, 'berjalan')",
            (stale_time,),
        )
        # Ambil active run -> stale run harus dibersihkan dan mengembalikan None
        active = job_runs_repo.get_active_fresh_run(conn, "scrape_cycle", max_minutes=30)
        assert active is None

        # Cek bahwa baris macet diubah menjadi gagal
        stale_row = conn.execute("SELECT status FROM job_runs ORDER BY id DESC LIMIT 1").fetchone()
        assert stale_row["status"] == "gagal"


def test_active_fresh_run_blocks_concurrent_cycle(test_db: Path) -> None:
    """Memastikan eksekusi siklus baru ditolak jika ada eksekusi segar (< 30 menit) yang masih berjalan."""
    fresh_time = (datetime.now() - timedelta(minutes=5)).isoformat()
    with connection.transaction(test_db) as conn:
        conn.execute(
            "INSERT INTO job_runs (job_name, trigger, started_at, status) VALUES ('scrape_cycle', 'terjadwal', ?, 'berjalan')",
            (fresh_time,),
        )

    with pytest.raises(RuntimeError, match="sedang berjalan"):
        run_cycle(trigger="manual", db_path=test_db)


def test_daily_digest_no_duplicates_and_fault_tolerance(test_db: Path) -> None:
    """Menguji digest harian tidak terkirim ganda dan toleran terhadap kegagalan salah satu pengiriman."""
    with connection.transaction(test_db) as conn:
        r1 = repos_repo.add_repo(conn, "owner/repo-1", kind="monitor")
        subscribers_repo.add_or_update_subscriber(conn, 201)
        subscribers_repo.add_or_update_subscriber(conn, 202)
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('201', ?)", (r1,))
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('202', ?)", (r1,))

    # Mock notifier: 201 gagal (exception), 202 berhasil
    notifier = MagicMock()

    def mock_send(chat_id: int, msg: str) -> bool:
        if str(chat_id) == "201":
            raise ConnectionError("Telegram network failure")
        return True

    notifier.send_message.side_effect = mock_send

    # Eksekusi digest pertama
    sent_count = send_daily_digest(digest_date="2026-05-10", notifier=notifier, db_path=test_db)
    assert sent_count == 1  # hanya 202 yang berhasil dicatat

    with connection.transaction(test_db) as conn:
        log_201 = conn.execute("SELECT * FROM digest_log WHERE chat_id = '201'").fetchone()
        log_202 = conn.execute("SELECT * FROM digest_log WHERE chat_id = '202'").fetchone()
        assert log_201 is None
        assert log_202 is not None

    # Eksekusi digest kedua di hari yang sama: 202 tidak dikirim ulang
    notifier.send_message.reset_mock()
    notifier.send_message.side_effect = lambda cid, msg: True
    sent_second = send_daily_digest(digest_date="2026-05-10", notifier=notifier, db_path=test_db)
    assert sent_second == 1  # sekarang 201 berhasil terkirim
    # pastikan 202 tidak dipanggil lagi
    calls = [call[0][0] for call in notifier.send_message.call_args_list]
    assert 202 not in calls


def test_scheduler_once_execution(monkeypatch, test_db: Path) -> None:
    """Menguji eksekusi CLI penjadwal dengan bendera --once."""
    called = []

    def mock_run_cycle(trigger: str = "manual"):
        called.append(trigger)
        return {"status": "berhasil"}

    monkeypatch.setattr("app.scheduler.__main__.run_cycle", mock_run_cycle)
    run_scheduler_main(["--once"])
    assert called == ["manual"]
