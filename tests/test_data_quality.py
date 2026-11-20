"""Pengujian aturan kualitas data pipeline latih Model A (M2-rev)."""
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app import config
from app.db import connection, init_db, training_rows_repo
from app.services.training_service import (
    _is_history_gap_exceeded,
    _process_single_repo,
    build_training_data,
)


def test_history_gap_detection(monkeypatch) -> None:
    """Memastikan deteksi gap commit pertama vs created_at membaca config.MAX_HISTORY_GAP_MONTHS."""
    monkeypatch.setattr(config, "MAX_HISTORY_GAP_MONTHS", 6)

    # 1. Gap 12 bulan (commit pertama Jan 2023, created_at Jan 2024) -> Terdeteksi
    first_dt_12m = "2023-01-01T00:00:00Z"
    created_at = "2024-01-01T00:00:00Z"
    assert _is_history_gap_exceeded(first_dt_12m, created_at) is True

    # 2. Gap 3 bulan (commit pertama Okt 2023, created_at Jan 2024) -> Tidak melebihi batas 6 bulan
    first_dt_3m = "2023-10-01T00:00:00Z"
    assert _is_history_gap_exceeded(first_dt_3m, created_at) is False

    # 3. Commit setelah repo created_at -> Tidak melebihi batas
    first_dt_after = "2024-02-01T00:00:00Z"
    assert _is_history_gap_exceeded(first_dt_after, created_at) is False


def test_data_quality_exclusions(tmp_path: Path, monkeypatch) -> None:
    """Menguji aturan kualitas data: work_items == 0, gap riwayat fork, created_at hilang."""
    db_file = tmp_path / "test_dq.db"
    init_db(db_file)

    mock_client = MagicMock()
    mock_runner = MagicMock()

    # Skenario 1: created_at tidak tersedia pada API GitHub
    mock_client.get_repo.return_value = {
        "full_name": "owner/norepo",
        "fork": False,
        "archived": False,
        "private": False,
        "created_at": None,
    }
    inc1, exc1 = _process_single_repo(
        entry={"full_name": "owner/norepo"},
        monitor_repos=[],
        client=mock_client,
        runner=mock_runner,
        db_path=db_file,
        delete_clones=False,
        refresh=True,
    )
    assert inc1 is None
    assert exc1 is not None
    assert exc1["reason"] == "data pembuatan repositori tidak tersedia"

    # Skenario 2: Riwayat commit diimpor / fork (commit 12 bulan sebelum created_at)
    mock_client.get_repo.return_value = {
        "full_name": "owner/forked",
        "fork": False,
        "archived": False,
        "private": False,
        "created_at": "2024-01-01T00:00:00Z",
    }
    # Mock git metrics: tag, first_dt, rel_dt, dur, n_contrib, kloc
    monkeypatch.setattr(
        "app.services.training_service._extract_git_metrics",
        lambda *args, **kwargs: ("v1.0.0", "2023-01-01T00:00:00Z", "2024-06-01T00:00:00Z", 17.0, 5, 10.0),
    )
    inc2, exc2 = _process_single_repo(
        entry={"full_name": "owner/forked"},
        monitor_repos=[],
        client=mock_client,
        runner=mock_runner,
        db_path=db_file,
        delete_clones=False,
        refresh=True,
    )
    assert inc2 is None
    assert exc2 is not None
    assert exc2["reason"] == "riwayat commit diimpor atau fork"

    # Skenario 3: n_work_items == 0 (jumlah issue+PR nol)
    mock_client.get_repo.return_value = {
        "full_name": "owner/nowork",
        "fork": False,
        "archived": False,
        "private": False,
        "created_at": "2024-01-01T00:00:00Z",
    }
    monkeypatch.setattr(
        "app.services.training_service._extract_git_metrics",
        lambda *args, **kwargs: ("v1.0.0", "2023-11-01T00:00:00Z", "2024-06-01T00:00:00Z", 7.0, 5, 10.0),
    )
    mock_client.search_count.return_value = 0  # 0 issue + 0 PR
    inc3, exc3 = _process_single_repo(
        entry={"full_name": "owner/nowork"},
        monitor_repos=[],
        client=mock_client,
        runner=mock_runner,
        db_path=db_file,
        delete_clones=False,
        refresh=True,
    )
    assert inc3 is None
    assert exc3 is not None
    assert "jumlah issue+PR nol" in exc3["reason"]

    # Skenario 4: Lolos validasi (commit 3 bulan sebelum created_at, n_work > 0)
    mock_client.get_repo.return_value = {
        "full_name": "owner/valid",
        "fork": False,
        "archived": False,
        "private": False,
        "created_at": "2024-01-01T00:00:00Z",
    }
    monkeypatch.setattr(
        "app.services.training_service._extract_git_metrics",
        lambda *args, **kwargs: ("v1.0.0", "2023-10-15T00:00:00Z", "2024-06-01T00:00:00Z", 7.5, 8, 12.0),
    )
    mock_client.search_count.return_value = 25  # > 0
    inc4, exc4 = _process_single_repo(
        entry={"full_name": "owner/valid"},
        monitor_repos=[],
        client=mock_client,
        runner=mock_runner,
        db_path=db_file,
        delete_clones=False,
        refresh=True,
    )
    assert exc4 is None
    assert inc4 is not None
    assert inc4["full_name"] == "owner/valid"
    assert inc4["n_work_items"] == 50  # 25 issue + 25 pr

    # Periksa catatan di database
    with connection.transaction(db_file) as conn:
        rows = training_rows_repo.list_training_rows(conn, included_only=False)
        assert len(rows) == 4
        included_rows = [r for r in rows if r["included"] == 1]
        excluded_rows = [r for r in rows if r["included"] == 0]
        assert len(included_rows) == 1
        assert len(excluded_rows) == 3
