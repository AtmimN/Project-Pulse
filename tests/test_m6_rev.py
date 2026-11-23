"""Pengujian komprehensif implementasi M6-rev (sesuai docs/instruction/10-revisi-m6.md)."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from flask.testing import FlaskClient
import pytest

from app.db import connection, repos_repo, snapshots_repo, training_rows_repo
from app.estimator.benchmark import calculate_duration_benchmark
from app.health.rules import (
    evaluate_mood,
    evaluate_overall,
    evaluate_speed,
    evaluate_workload,
)
from app.services import health_service


def test_benchmark_duration_calculation_small_data() -> None:
    """1. benchmark_duration.json: median dan kuartil benar untuk data kecil."""
    durations = [2.0, 4.0, 6.0, 8.0, 10.0]
    bench = calculate_duration_benchmark(durations)
    assert bench["n"] == 5
    assert bench["min"] == 2.0
    assert bench["max"] == 10.0
    assert bench["median"] == 6.0
    assert bench["q1"] == 4.0
    assert bench["q3"] == 8.0
    assert "built_at" in bench


def test_estimate_page_only_model_b_no_model_a(client: FlaskClient) -> None:
    """2. Halaman estimasi tidak memuat kartu Model A dan hasil Model B tetap benar."""
    res = client.get("/estimasi")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    # Memastikan kartu Model A tidak ada di UI
    assert "id=\"cardModelA\"" not in html
    assert "Model A &mdash; Pola Historis" not in html
    assert "Mengapa Model A dan Model B bisa berlawanan arah?" not in html
    assert "Uji Mundur Rilis Pertama" not in html

    # Model B dan Konteks GitHub tetap tampil
    assert "Model B" in html
    assert "Konteks dari Data Historis GitHub" in html
    assert "Satuan, Asumsi, dan Keterbatasan" in html


def test_prefill_contract_m6_rev(client: FlaskClient, temp_db_path: Path) -> None:
    """3. Prefill mengisi KLOC dan n_tasks, menolak first_stable, 404 jika snapshot tidak ada."""
    with connection.transaction(temp_db_path) as conn:
        r_id = repos_repo.add_repo(conn, "octocat/hello-world", "monitor", 1)
        snapshots_repo.save_snapshot(
            conn, r_id, "now", n_contributors=12, n_work_items=45, kloc=14.2
        )

    # Valid prefill now
    res = client.get("/api/estimate/prefill?repo=octocat/hello-world&as_of=now")
    assert res.status_code == 200
    d = res.get_json()
    assert d["kloc"] == 14.2
    assert d["n_tasks"] == 45
    assert "n_members" not in d
    assert "alasan_anggota" in d

    # Snapshot tidak ada -> 404 dengan snapshot_tidak_tersedia
    res_404 = client.get("/api/estimate/prefill?repo=owner/nonexistent&as_of=now")
    assert res_404.status_code == 404
    assert res_404.get_json()["error"] == "snapshot_tidak_tersedia"

    # Nama tidak valid -> 400
    res_bad_name = client.get("/api/estimate/prefill?repo=invalidname&as_of=now")
    assert res_bad_name.status_code == 400
    assert res_bad_name.get_json()["error"] == "invalid_repo"

    # as_of=first_stable ditolak -> 400
    res_stable = client.get("/api/estimate/prefill?repo=octocat/hello-world&as_of=first_stable")
    assert res_stable.status_code == 400
    assert res_stable.get_json()["error"] == "invalid_as_of"


def test_findings_panel_and_negative_improvement(client: FlaskClient, monkeypatch) -> None:
    """4. Panel temuan: improvement_pct <= 0 memunculkan 'tidak lebih baik dari tebakan median'."""
    from app.services import dashboard_service
    orig_fn = dashboard_service.get_regression_a_data

    def mock_get_a(*args, **kwargs):
        d = orig_fn(*args, **kwargs)
        if d:
            d = dict(d)
            d["improvement_pct"] = -8.5
            d["diagnostics"] = {
                "finding": "korelasi lemah (ρ = 0.12); jumlah kontributor tidak memprediksi durasi pada data ini",
                "spearman_correlation": {
                    "duration_vs_n_contributors": 0.12,
                    "duration_vs_n_work_items": 0.15,
                    "duration_vs_kloc": -0.05,
                },
                "sign_stability": {"n_contributors": 60.0, "n_work_items": 80.0, "kloc": 50.0},
                "standardized_coefficients": {"n_contributors": 0.2, "n_work_items": 0.5, "kloc": 0.1},
            }
        return d

    monkeypatch.setattr(dashboard_service, "get_regression_a_data", mock_get_a)

    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Temuan Evaluasi Durasi GitHub" in html
    assert "model durasi dari data GitHub tidak lebih baik dari tebakan median" in html
    assert "tidak dipakai sebagai prediktor estimasi" in html
    assert "chart-model-a" not in html


def test_model_b_scatter_distinct_empty_messages() -> None:
    """5. Scatter Model B: pesan kosong terpisah untuk 3 keadaan pada dashboard.js."""
    js_content = Path("app/web/static/js/dashboard.js").read_text(encoding="utf-8")
    assert "Model B belum dilatih atau berkas model belum tersedia." in js_content
    assert "Metrik evaluasi tidak memuat data pasangan prediksi (pairs)." in js_content
    assert "Jumlah sampel pasangan prediksi tidak mencukupi untuk ditampilkan." in js_content
    assert "chart-model-a" not in js_content


def test_health_dimension_boundary_rules() -> None:
    """6. Kartu Kesehatan: tiap dimensi memberi warna benar pada batas nilai (89, 90, 74, 75) dll."""
    # Kecepatan batas 74 (hijau), 75 (kuning), 89 (kuning), 90 (merah)
    assert evaluate_speed(74.0, False, 10.0).status == "hijau"
    assert evaluate_speed(75.0, False, 10.0).status == "kuning"
    assert evaluate_speed(89.0, False, 10.0).status == "kuning"
    assert evaluate_speed(90.0, False, 10.0).status == "merah"
    assert evaluate_speed(None, False, None).status == "abu-abu"

    # Beban batas 74 (hijau), 75 (kuning), 89 (kuning), 90 (merah)
    assert evaluate_workload(74.0, 5.0).status == "hijau"
    assert evaluate_workload(75.0, 5.0).status == "kuning"
    assert evaluate_workload(89.0, 5.0).status == "kuning"
    assert evaluate_workload(90.0, 5.0).status == "merah"
    assert evaluate_workload(None, None).status == "abu-abu"

    # Suasana: indeks -0.11 -> merah; alert kuat 14 hari -> merah; data kurang -> abu-abu
    assert evaluate_mood(-0.11, comments_count=20, min_comments=10).status == "merah"
    assert evaluate_mood(0.05, comments_count=20, min_comments=10, has_strong_alert_14d=True).status == "merah"
    assert evaluate_mood(0.05, comments_count=20, min_comments=10, has_medium_alert_14d=True).status == "kuning"
    assert evaluate_mood(0.15, comments_count=20, min_comments=10).status == "hijau"
    assert evaluate_mood(0.20, comments_count=5, min_comments=10).status == "abu-abu"

    # Ringkasan keseluruhan: merah jika ada >= 1 merah; kuning jika ada >= 1 kuning; hijau jika semua hijau
    d_red = evaluate_speed(92.0, False, 15.0)
    d_green = evaluate_workload(50.0, 3.0)
    d_yellow = evaluate_workload(80.0, 7.0)

    st_red, r_red = evaluate_overall([d_red, d_green])
    assert st_red == "merah" and len(r_red) > 0

    st_yel, r_yel = evaluate_overall([d_green, d_yellow])
    assert st_yel == "kuning" and len(r_yel) > 0

    st_grn, r_grn = evaluate_overall([d_green])
    assert st_grn == "hijau" and len(r_grn) > 0


def test_health_service_no_network_or_git_calls(client: FlaskClient, temp_db_path: Path, monkeypatch) -> None:
    """7. Kartu Kesehatan dan /api/health tidak memanggil GitHub atau git."""
    import requests
    import subprocess

    def fail_requests(*args, **kwargs):
        pytest.fail("Kartu kesehatan tidak boleh memanggil requests/jaringan!")

    def fail_subprocess(*args, **kwargs):
        pytest.fail("Kartu kesehatan tidak boleh memanggil subprocess/git!")

    monkeypatch.setattr(requests, "get", fail_requests)
    monkeypatch.setattr(subprocess, "run", fail_subprocess)

    # Tambahkan repo pantau tanpa snapshot
    with connection.transaction(temp_db_path) as conn:
        repos_repo.add_repo(conn, "dummy/test-repo", "monitor", 1)

    # Akses rute HTML dan API
    res_list = client.get("/kesehatan")
    assert res_list.status_code == 200

    res_detail = client.get("/kesehatan?repo=dummy/test-repo")
    assert res_detail.status_code == 200
    assert "dummy/test-repo" in res_detail.get_data(as_text=True)

    res_api = client.get("/api/health?repo=dummy/test-repo")
    assert res_api.status_code == 200
    d = res_api.get_json()
    assert d["repo"] == "dummy/test-repo"
    assert "overall_status" in d


def test_health_module_pure_architecture() -> None:
    """8. Arsitektur: app/health/ murni (tanpa Flask, requests, atau subprocess)."""
    rules_code = Path("app/health/rules.py").read_text(encoding="utf-8")
    assert "flask" not in rules_code.lower()
    assert "requests" not in rules_code.lower()
    assert "subprocess" not in rules_code.lower()
    assert "sqlite3" not in rules_code.lower()
