"""Pengujian aturan alert, tier kekuatan, deduplikasi, dan backtest."""
from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from app.alerts.engine import (
    check_kata_kunci,
    check_lonjakan_negatif,
    check_rilis_bermasalah,
    check_sentimen_turun,
    evaluate_all_rules,
)
from app.db import alerts_repo, connection, repos_repo, subscribers_repo
from app.services.alert_service import backtest_alerts, evaluate_and_save_alerts


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Membuat database sementara dengan skema lengkap."""
    db_file = tmp_path / "test_alerts.db"
    conn = sqlite3.connect(db_file)
    schema_sql = (Path(__file__).resolve().parent.parent / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.close()
    return db_file


def test_alert_thresholds_and_tiers() -> None:
    """Menguji ambang minimal dan pemetaan tier (lemah, sedang, kuat) untuk tiap jenis alert."""
    # 1. sentimen_turun: min 10 komentar di tiap jendela. Ambang: drop >= 0.10, 0.15, 0.25
    stats_low = [
        {"stat_date": "2026-05-10", "n_comments": 5, "n_positive": 5, "n_negative": 0},
        {"stat_date": "2026-04-10", "n_comments": 5, "n_positive": 0, "n_negative": 5},
    ]
    assert check_sentimen_turun(stats_low, "2026-05-10", repo_id=1) is None

    # Tiers: 30d prev has 100 comments (pos=80, neg=20 -> idx = 0.60)
    base_30 = [{"stat_date": f"2026-04-{i:02d}", "n_comments": 10, "n_positive": 8, "n_negative": 2} for i in range(10, 20)]
    # Lemah: drop >= 0.10, < 0.15 (pos=74, neg=26 -> idx_7d = 0.48 -> drop = 0.12)
    s_lemah = base_30 + [{"stat_date": "2026-05-10", "n_comments": 100, "n_positive": 74, "n_negative": 26}]
    res = check_sentimen_turun(s_lemah, "2026-05-10", 1)
    assert res is not None and res["strength"] == "lemah"

    # Sedang: drop >= 0.15, < 0.25 (pos=70, neg=30 -> idx_7d = 0.40 -> drop = 0.20)
    s_sedang = base_30 + [{"stat_date": "2026-05-10", "n_comments": 100, "n_positive": 70, "n_negative": 30}]
    res = check_sentimen_turun(s_sedang, "2026-05-10", 1)
    assert res is not None and res["strength"] == "sedang"

    # Kuat: drop >= 0.25 (pos=60, neg=40 -> idx_7d = 0.20 -> drop = 0.40)
    s_kuat = base_30 + [{"stat_date": "2026-05-10", "n_comments": 100, "n_positive": 60, "n_negative": 40}]
    res = check_sentimen_turun(s_kuat, "2026-05-10", 1)
    assert res is not None and res["strength"] == "kuat"

    # 2. lonjakan_negatif: min 3 negatif hari ini. Ambang: 1.5x, 2.0x, 3.0x
    stats_lonjakan = [{"stat_date": "2026-05-01", "n_comments": 30, "n_positive": 0, "n_negative": 30}]
    # avg 30d = 30 / 30 = 1.0 per hari
    assert check_lonjakan_negatif(stats_lonjakan + [{"stat_date": "2026-05-10", "n_negative": 2}], "2026-05-10", 1) is None
    # 3 neg today -> ratio = 3.0 -> kuat
    res_ln = check_lonjakan_negatif(stats_lonjakan + [{"stat_date": "2026-05-10", "n_negative": 3}], "2026-05-10", 1)
    assert res_ln is not None and res_ln["strength"] == "kuat"

    # 3. kata_kunci: hits >= 2 (lemah), >= 3 (sedang), >= 5 (kuat)
    assert len(check_kata_kunci([{"stat_date": "2026-05-10", "keyword": "bug", "n_hits": 1}], "2026-05-10", 1)) == 0
    res_k2 = check_kata_kunci([{"stat_date": "2026-05-10", "keyword": "bug", "n_hits": 2}], "2026-05-10", 1)
    assert res_k2[0]["strength"] == "lemah"
    res_k3 = check_kata_kunci([{"stat_date": "2026-05-10", "keyword": "bug", "n_hits": 3}], "2026-05-10", 1)
    assert res_k3[0]["strength"] == "sedang"
    res_k5 = check_kata_kunci([{"stat_date": "2026-05-10", "keyword": "bug", "n_hits": 5}], "2026-05-10", 1)
    assert res_k5[0]["strength"] == "kuat"


def test_sentimen_turun_window_bounds() -> None:
    """Menguji bahwa jendela 7 hari [D-6 s/d D] dan jendela pembanding [D-36 s/d D-7] terhitung tepat."""
    alert_date = "2026-05-10"
    ref_dt = datetime.fromisoformat(alert_date)

    # D-37 (keluar batas pembanding), D-36 (masuk pembanding), D-7 (masuk pembanding), D-6 (masuk jendela 7h)
    d_minus_37 = (ref_dt - timedelta(days=37)).strftime("%Y-%m-%d")
    d_minus_36 = (ref_dt - timedelta(days=36)).strftime("%Y-%m-%d")
    d_minus_7 = (ref_dt - timedelta(days=7)).strftime("%Y-%m-%d")
    d_minus_6 = (ref_dt - timedelta(days=6)).strftime("%Y-%m-%d")

    # Masukkan 10 komentar di D-37 (tidak boleh terhitung di 30d prev)
    stats = [{"stat_date": d_minus_37, "n_comments": 10, "n_positive": 10, "n_negative": 0}]
    assert check_sentimen_turun(stats, alert_date, 1) is None

    # Tambahkan di D-36 dan D-7 (total 10 komentar pembanding)
    stats.extend([
        {"stat_date": d_minus_36, "n_comments": 5, "n_positive": 5, "n_negative": 0},
        {"stat_date": d_minus_7, "n_comments": 5, "n_positive": 5, "n_negative": 0},
    ])
    # Tambahkan 10 komentar di D-6 (jendela 7h) dengan negatif penuh
    stats.append({"stat_date": d_minus_6, "n_comments": 10, "n_positive": 0, "n_negative": 10})

    res = check_sentimen_turun(stats, alert_date, 1)
    assert res is not None
    assert res["detail"]["comments_30d"] == 10
    assert res["detail"]["comments_7d"] == 10
    assert res["strength"] == "kuat"


def test_rilis_bermasalah_draft_and_window() -> None:
    """Menguji bahwa rilis draft dan rilis di luar 3 hari terakhir diabaikan."""
    alert_date = "2026-05-10"
    # Rilis draft -> diabaikan
    rel_draft = [{"tag": "v1.0.0", "published_at": "2026-05-09T10:00:00", "is_draft": 1}]
    stats = [{"stat_date": "2026-05-10", "n_comments": 20, "n_positive": 0, "n_negative": 20}]
    assert check_rilis_bermasalah(stats, rel_draft, alert_date, 1) == []

    # Rilis 4 hari lalu (> 3 hari) -> diabaikan
    rel_old = [{"tag": "v1.0.0", "published_at": "2026-05-06T10:00:00", "is_draft": 0}]
    assert check_rilis_bermasalah(stats, rel_old, alert_date, 1) == []

    # Rilis 2 hari lalu (< 8 komentar) -> diabaikan
    rel_valid = [{"tag": "v1.0.0", "published_at": "2026-05-08T10:00:00", "is_draft": 0}]
    stats_few = [{"stat_date": "2026-05-09", "n_comments": 5, "n_positive": 0, "n_negative": 5}]
    assert check_rilis_bermasalah(stats_few, rel_valid, alert_date, 1) == []

    # Rilis 2 hari lalu (>= 8 komentar, prop negatif 100% vs 0% pra-rilis) -> kuat
    stats_ok = [{"stat_date": "2026-05-09", "n_comments": 10, "n_positive": 0, "n_negative": 10}]
    res = check_rilis_bermasalah(stats_ok, rel_valid, alert_date, 1)
    assert len(res) == 1
    assert res[0]["strength"] == "kuat"
    assert res[0]["dedupe_key"] == "rilis_bermasalah:1:2026-05-10:v1.0.0"


def test_alert_deduplication(test_db: Path) -> None:
    """Memastikan evaluasi ulang di hari yang sama tidak menduplikasi alert di database."""
    with connection.transaction(test_db) as conn:
        rid = repos_repo.add_repo(conn, "owner/pantau-1", kind="monitor")
        # Masukkan kata kunci kritis yang memicu alert
        conn.execute("INSERT INTO keyword_daily (repo_id, keyword, stat_date, n_hits) VALUES (?, 'crash', '2026-05-10', 5)", (rid,))

    # Evaluasi pertama
    res1 = evaluate_and_save_alerts(alert_date="2026-05-10", db_path=test_db)
    assert len(res1) == 1

    # Evaluasi kedua di hari yang sama
    res2 = evaluate_and_save_alerts(alert_date="2026-05-10", db_path=test_db)
    assert len(res2) == 0

    with connection.transaction(test_db) as conn:
        alerts = conn.execute("SELECT * FROM alerts WHERE repo_id = ?", (rid,)).fetchall()
        assert len(alerts) == 1


def test_subscriber_sensitivity_and_watchlist(test_db: Path) -> None:
    """Menguji penyaringan pengiriman alert berdasarkan keaktifan, watchlist, dan sensitivitas."""
    with connection.transaction(test_db) as conn:
        r1 = repos_repo.add_repo(conn, "owner/repo-1", kind="monitor")
        r2 = repos_repo.add_repo(conn, "owner/repo-2", kind="monitor")

        # Pelanggan
        # A: tinggi, r1
        subscribers_repo.add_or_update_subscriber(conn, 101, sensitivity="tinggi")
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('101', ?)", (r1,))

        # B: sedang, r1
        subscribers_repo.add_or_update_subscriber(conn, 102, sensitivity="sedang")
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('102', ?)", (r1,))

        # C: rendah, r1
        subscribers_repo.add_or_update_subscriber(conn, 103, sensitivity="rendah")
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('103', ?)", (r1,))

        # D: nonaktif, r1
        subscribers_repo.add_or_update_subscriber(conn, 104, sensitivity="tinggi")
        subscribers_repo.set_active(conn, 104, 0)
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('104', ?)", (r1,))

        # E: tinggi, r2 (bukan r1)
        subscribers_repo.add_or_update_subscriber(conn, 105, sensitivity="tinggi")
        conn.execute("INSERT INTO watchlist (chat_id, repo_id) VALUES ('105', ?)", (r2,))

        # Test filter repo1
        subs_lemah = alerts_repo.get_subscribers_for_alert(conn, r1, "lemah")
        assert [s["chat_id"] for s in subs_lemah] == [101]

        subs_sedang = alerts_repo.get_subscribers_for_alert(conn, r1, "sedang")
        assert sorted([s["chat_id"] for s in subs_sedang]) == [101, 102]

        subs_kuat = alerts_repo.get_subscribers_for_alert(conn, r1, "kuat")
        assert sorted([s["chat_id"] for s in subs_kuat]) == [101, 102, 103]


def test_backtest_alerts_no_side_effects(test_db: Path, tmp_path: Path) -> None:
    """Menguji bahwa backtest-alerts tidak menulis ke tabel alerts dan menghasilkan CSV yang benar."""
    out_csv = tmp_path / "backtest_result.csv"
    recent_date = (datetime.now().date() - timedelta(days=2)).strftime("%Y-%m-%d")
    with connection.transaction(test_db) as conn:
        rid = repos_repo.add_repo(conn, "owner/repo-backtest", kind="monitor")
        conn.execute(
            "INSERT INTO keyword_daily (repo_id, keyword, stat_date, n_hits) VALUES (?, 'memory_leak', ?, 6)",
            (rid, recent_date),
        )

    res = backtest_alerts(days=30, repo_name="owner/repo-backtest", output_csv=out_csv, db_path=test_db)
    assert res["total_alerts"] >= 1
    assert out_csv.exists()

    # Pastikan tabel alerts tetap kosong
    with connection.transaction(test_db) as conn:
        count = conn.execute("SELECT COUNT(*) as c FROM alerts").fetchone()["c"]
        assert count == 0
