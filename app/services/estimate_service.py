"""Layanan logika bisnis kalkulasi estimasi Model B (NASA93) dan konteks GitHub."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import joblib

from app import config
from app.db import connection, estimations_repo, repos_repo, snapshots_repo, training_rows_repo
from app.estimator.adjustments import average_member_levels
from app.estimator.benchmark import calculate_duration_benchmark, load_duration_benchmark
from app.estimator.model_b import MODEL_B_PATH, predict_model_b
from app.estimator.nasa93 import ORDINAL_MAP
from app.estimator.workload import analyze_workload


def get_prefill_data(
    repo_name: str,
    as_of: str = "now",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mengambil metrik ukuran dan tugas dari snapshot 'now' repositori pantau."""
    from app.scraper.repo_metrics import validate_repo_name
    if not validate_repo_name(repo_name):
        raise ValueError(f"Nama repositori '{repo_name}' tidak valid.")
    if as_of != "now":
        raise ValueError("Hanya snapshot 'now' yang didukung untuk prefill.")

    with connection.transaction(db_path) as conn:
        repo = repos_repo.get_by_full_name(conn, repo_name)
        if not repo:
            raise LookupError(f"Repositori '{repo_name}' tidak ditemukan di database.")
        snapshot = snapshots_repo.get_snapshot(conn, repo["id"], "now")
        if not snapshot:
            raise LookupError(f"Data snapshot 'now' belum tersedia untuk {repo_name}.")

    return {
        "repo": repo["full_name"],
        "as_of": "now",
        "n_tasks": snapshot.get("n_work_items"),
        "kloc": snapshot.get("kloc"),
        "alasan_anggota": (
            "Jumlah kontributor kumulatif repositori bukan ukuran tim aktif; "
            "memakainya sebagai pembagi usaha menghasilkan durasi yang tidak masuk akal."
        ),
    }


def _validate_input_numbers(n_members: int, n_tasks: int, kloc: float) -> None:
    """Memvalidasi batasan nilai input numerik form estimasi."""
    if not (1 <= n_members <= 300):
        raise ValueError("Jumlah anggota tim harus antara 1 dan 300.")
    if not (1 <= n_tasks <= 100000):
        raise ValueError("Jumlah tugas/issue harus antara 1 dan 100.000.")
    if not (0.1 <= kloc <= 5000.0):
        raise ValueError("Ukuran proyek (KLOC) harus antara 0.1 dan 5000.")


def _parse_estimation_inputs(payload: dict[str, Any]) -> tuple[int, int, float, Any, Any, Any]:
    """Mengurai input form atau daftar anggota tim ke dalam variabel estimasi."""
    members_list = payload.get("members")
    if members_list and isinstance(members_list, list):
        avg_info = average_member_levels(members_list)
        return (
            avg_info["n_members"], int(payload.get("n_tasks", 10)), float(payload.get("kloc", 5.0)),
            avg_info["avg_acap_ord"], avg_info["avg_pcap_ord"], avg_info["avg_aexp_ord"],
        )
    return (
        int(payload.get("n_members", 1)), int(payload.get("n_tasks", 10)), float(payload.get("kloc", 5.0)),
        payload.get("acap", "nominal"), payload.get("pcap", "nominal"), payload.get("aexp", "nominal"),
    )


def calculate_estimation(
    payload: dict[str, Any],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Menghitung estimasi proyek pada Model B (NASA93) dan konteks data GitHub."""
    n_members, n_tasks, kloc, acap_val, pcap_val, aexp_val = _parse_estimation_inputs(payload)
    _validate_input_numbers(n_members, n_tasks, kloc)

    acap_ord = float(ORDINAL_MAP.get(str(acap_val).lower(), acap_val if isinstance(acap_val, (int, float)) else 3))
    pcap_ord = float(ORDINAL_MAP.get(str(pcap_val).lower(), pcap_val if isinstance(pcap_val, (int, float)) else 3))
    aexp_ord = float(ORDINAL_MAP.get(str(aexp_val).lower(), aexp_val if isinstance(aexp_val, (int, float)) else 3))

    model_b_res = _calc_model_b(kloc, acap_ord, pcap_ord, aexp_ord, n_members)
    workload_res = _calc_workload(n_members, n_tasks, db_path)
    bench_res = _calc_duration_benchmark(db_path)

    response = {
        "model_b": model_b_res,
        "workload": workload_res,
        "benchmark_duration": bench_res,
        "input_summary": {
            "n_members": n_members, "n_tasks": n_tasks, "kloc": kloc,
            "acap": acap_val, "pcap": pcap_val, "aexp": aexp_val,
        },
    }

    with connection.transaction(db_path) as conn:
        estimations_repo.save_estimation(conn, payload, response)

    return response


def _calc_duration_benchmark(db_path: str | Path | None) -> dict[str, Any]:
    """Mengambil benchmark durasi dari berkas benchmark_duration.json atau basis data."""
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


def _calc_model_b(
    kloc: float,
    acap_ord: float,
    pcap_ord: float,
    aexp_ord: float,
    n_members: int,
) -> dict[str, Any]:
    """Kalkulasi internal untuk Model B."""
    if not MODEL_B_PATH.exists():
        return {
            "status": "untrained",
            "message": "Model B belum dilatih. Jalankan python -m app.cli train-models.",
        }
    bundle = joblib.load(MODEL_B_PATH)
    effort, dur_b, mae_effort, warnings = predict_model_b(
        bundle, kloc, acap_ord, pcap_ord, aexp_ord, n_members
    )
    mae_dur = round(mae_effort / max(1, n_members), 2)
    return {
        "status": "ready",
        "effort_person_months": effort,
        "indicative_duration": dur_b,
        "mae_effort": mae_effort,
        "mae_duration": mae_dur,
        "range": [max(0.1, round(dur_b - mae_dur, 2)), round(dur_b + mae_dur, 2)],
        "warnings": warnings,
    }


def _get_workload_dist(conn: Any) -> list[float]:
    """Mengambil sebaran rasio tugas per kontributor dari baris data latih."""
    dist = []
    for r in training_rows_repo.list_training_rows(conn, included_only=True):
        c, w = r.get("n_contributors"), r.get("n_work_items")
        if c and w:
            dist.append(float(w) / float(c))
    return dist


def _calc_workload(
    n_members: int,
    n_tasks: int,
    db_path: str | Path | None,
) -> dict[str, Any]:
    """Menghitung beban kerja berdasarkan sebaran rasio data latih."""
    dist: list[float] = []
    try:
        with connection.transaction(db_path) as conn:
            dist = _get_workload_dist(conn)
    except Exception as err:
        import logging
        logging.getLogger(__name__).debug("Gagal memuat distribusi beban data latih: %s", err)
    return analyze_workload(n_members, n_tasks, dist if dist else None)
