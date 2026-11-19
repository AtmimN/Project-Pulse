"""Pengujian skema database mode WAL dan fungsi repositori."""
from pathlib import Path
import sqlite3

from app.db.connection import get_connection
from app.db import (
    repos_repo,
    conversations_repo,
    job_runs_repo,
    keywords_repo,
    estimations_repo,
    subscribers_repo,
    alerts_repo,
)


def test_db_wal_mode_and_foreign_keys(temp_db_path: Path) -> None:
    """Memverifikasi bahwa koneksi menerapkan mode WAL dan foreign keys aktif."""
    conn = get_connection(temp_db_path)
    try:
        jm = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert jm.lower() == "wal"
        assert fk == 1
    finally:
        conn.close()


def test_repos_repo_crud(temp_db_path: Path) -> None:
    """Menguji penambahan, pencarian, dan pembaruan repositori."""
    conn = get_connection(temp_db_path)
    try:
        repo_id = repos_repo.add_repo(conn, "plankanban/planka", "monitor", 1)
        assert repo_id > 0

        repo = repos_repo.get_by_id(conn, repo_id)
        assert repo is not None
        assert repo["full_name"] == "plankanban/planka"
        assert repo["kind"] == "monitor"

        by_name = repos_repo.get_by_full_name(conn, "PLANKANBAN/PLANKA")
        assert by_name is not None
        assert by_name["id"] == repo_id

        all_monitor = repos_repo.list_repos(conn, kind="monitor", active_only=True)
        assert len(all_monitor) == 1

        repos_repo.set_active(conn, repo_id, 0)
        active_list = repos_repo.list_repos(conn, active_only=True)
        assert len(active_list) == 0
    finally:
        conn.close()


def test_initial_keywords(temp_db_path: Path) -> None:
    """Memastikan kata kunci bawaan (crash, login, error, broken, regression) terisi."""
    conn = get_connection(temp_db_path)
    try:
        kws = [k["word"] for k in keywords_repo.list_keywords(conn)]
        assert "crash" in kws
        assert "login" in kws
        assert "error" in kws
        assert "broken" in kws
        assert "regression" in kws
    finally:
        conn.close()


def test_conversations_and_job_runs(temp_db_path: Path) -> None:
    """Menguji pencatatan log percakapan dan siklus tugas."""
    conn = get_connection(temp_db_path)
    try:
        log_id = conversations_repo.log_conversation(
            conn, "sess-1", "halo bot", "halo juga", "Greeting"
        )
        assert log_id > 0
        logs = conversations_repo.list_conversations(conn, limit=10)
        assert len(logs) == 1
        assert logs[0]["message"] == "halo bot"

        job_id = job_runs_repo.start_job(conn, "scrape_cycle", "terjadwal")
        assert job_id > 0
        job_runs_repo.finish_job(conn, job_id, "berhasil", new_comments=15)
        latest = job_runs_repo.get_latest_run(conn, "scrape_cycle")
        assert latest is not None
        assert latest["status"] == "berhasil"
        assert latest["new_comments"] == 15
    finally:
        conn.close()
