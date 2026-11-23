"""Pengujian integrasi layanan estimasi dan API /api/estimate."""
from pathlib import Path
from flask.testing import FlaskClient

from app.db import connection, estimations_repo, repos_repo, snapshots_repo
from app.services.estimate_service import calculate_estimation, get_prefill_data


def test_prefill_from_snapshots(temp_db_path: Path) -> None:
    """Memastikan fitur prefill mengisi KLOC dan n_tasks, dan tidak mengisi anggota atau level."""
    with connection.transaction(temp_db_path) as conn:
        repo_id = repos_repo.add_repo(conn, "plankanban/planka", "monitor", 1)
        snapshots_repo.save_snapshot(
            conn=conn,
            repo_id=repo_id,
            as_of="now",
            n_contributors=8,
            n_work_items=120,
            kloc=25.5,
        )

    # Prefill now
    data_now = get_prefill_data("plankanban/planka", as_of="now", db_path=temp_db_path)
    assert data_now["n_tasks"] == 120
    assert data_now["kloc"] == 25.5
    assert "n_members" not in data_now
    assert "acap" not in data_now
    assert "alasan_anggota" in data_now

    # first_stable tidak lagi diterima (ValueError)
    try:
        get_prefill_data("plankanban/planka", as_of="first_stable", db_path=temp_db_path)
        assert False, "as_of=first_stable harus ditolak"
    except ValueError as e:
        assert "now" in str(e)


def test_calculate_estimation_and_persistence(temp_db_path: Path) -> None:
    """Menguji eksekusi kalkulasi estimasi Model B dan penyimpanan ke basis data."""
    payload = {
        "n_members": 5,
        "n_tasks": 50,
        "kloc": 15.0,
        "acap": "nominal",
        "pcap": "tinggi",
        "aexp": "nominal",
    }
    result = calculate_estimation(payload, db_path=temp_db_path)
    assert "model_b" in result
    assert "workload" in result
    assert "benchmark_duration" in result
    assert "model_a" not in result

    with connection.transaction(temp_db_path) as conn:
        saved = estimations_repo.list_recent_estimations(conn, limit=5)
        assert len(saved) >= 1
        assert saved[0]["input"]["n_members"] == 5


def test_api_estimate_endpoints(client: FlaskClient, temp_db_path: Path) -> None:
    """Menguji API endpoint /api/estimate/prefill dan /api/estimate."""
    # 1. Prefill repo tidak valid -> 400
    r_bad_name = client.get("/api/estimate/prefill?repo=repo_palsu_tanpa_slash&as_of=now")
    assert r_bad_name.status_code == 400
    assert r_bad_name.get_json()["error"] == "invalid_repo"

    # 2. Prefill repo tidak ditemukan / snapshot belum ada -> 404
    r_not_found = client.get("/api/estimate/prefill?repo=pemilik/repo-tidak-ada&as_of=now")
    assert r_not_found.status_code == 404
    assert r_not_found.get_json()["error"] == "snapshot_tidak_tersedia"

    # 3. as_of bukan now -> 400
    r_bad_as_of = client.get("/api/estimate/prefill?repo=pemilik/repo&as_of=first_stable")
    assert r_bad_as_of.status_code == 400
    assert r_bad_as_of.get_json()["error"] == "invalid_as_of"

    # 4. Input tidak valid -> 400
    r_bad_input = client.post("/api/estimate", json={"n_members": 500, "n_tasks": 10, "kloc": 5.0})
    assert r_bad_input.status_code == 400
    assert "antara 1 dan 300" in r_bad_input.get_json()["error"]

    # 5. Input valid -> 200
    valid_payload = {
        "n_members": 4,
        "n_tasks": 35,
        "kloc": 8.0,
        "acap": "nominal",
        "pcap": "nominal",
        "aexp": "nominal",
    }
    r_valid = client.post("/api/estimate", json=valid_payload)
    assert r_valid.status_code == 200
    res = r_valid.get_json()
    assert "model_b" in res
    assert "model_a" not in res
    assert "benchmark_duration" in res
