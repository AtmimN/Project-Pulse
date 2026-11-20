"""Layanan logika bisnis kalkulasi estimasi dua model berdampingan."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import joblib

from app import config
from app.db import connection, estimations_repo, repos_repo, snapshots_repo, training_rows_repo
from app.estimator.adjustments import average_member_levels, calculate_adjustment_factor
from app.estimator.comparison import compare_models
from app.estimator.model_a import MODEL_A_PATH, predict_model_a
from app.estimator.model_b import MODEL_B_PATH, predict_model_b
from app.estimator.nasa93 import ORDINAL_MAP, load_cocomo_multipliers
from app.estimator.workload import analyze_workload


def get_prefill_data(
    repo_name: str,
    as_of: str = "now",
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mengambil metrik repositori pantau dari repo_snapshots untuk mengisi otomatis form."""
    with connection.transaction(db_path) as conn:
        repo = repos_repo.get_by_full_name(conn, repo_name)
        if not repo:
            raise ValueError(f"Repositori '{repo_name}' tidak ditemukan.")
        snapshot = snapshots_repo.get_snapshot(conn, repo["id"], as_of)
        if not snapshot:
            raise ValueError(f"Data snapshot '{as_of}' belum tersedia untuk {repo_name}.")

    return {
        "repo": repo["full_name"],
        "as_of": as_of,
        "n_members": snapshot.get("n_contributors"),
        "n_tasks": snapshot.get("n_work_items"),
        "kloc": snapshot.get("kloc"),
        "duration_actual": snapshot.get("duration_months"),
    }


def _validate_input_numbers(n_members: int, n_tasks: int, kloc: float) -> None:
    """Memvalidasi batasan nilai input numerik form estimasi."""
    if not (1 <= n_members <= 300):
        raise ValueError("Jumlah anggota tim harus antara 1 dan 300.")
    if not (1 <= n_tasks <= 100000):
        raise ValueError("Jumlah tugas/issue harus antara 1 dan 100.000.")
    if not (0.1 <= kloc <= 5000.0):
        raise ValueError("Ukuran proyek (KLOC) harus antara 0.1 dan 5000.")


def calculate_estimation(
    payload: dict[str, Any],
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Menghitung estimasi proyek pada Model A dan Model B secara berdampingan."""
    members_list = payload.get("members")
    if members_list and isinstance(members_list, list):
        avg_info = average_member_levels(members_list)
        n_members = avg_info["n_members"]
        acap_val = avg_info["avg_acap_ord"]
        pcap_val = avg_info["avg_pcap_ord"]
        aexp_val = avg_info["avg_aexp_ord"]
    else:
        n_members = int(payload.get("n_members", 1))
        acap_val = payload.get("acap", "nominal")
        pcap_val = payload.get("pcap", "nominal")
        aexp_val = payload.get("aexp", "nominal")

    n_tasks = int(payload.get("n_tasks", 10))
    kloc = float(payload.get("kloc", 5.0))
    _validate_input_numbers(n_members, n_tasks, kloc)

    # 1. Model A
    model_a_res = _calc_model_a(n_members, n_tasks, kloc, acap_val, pcap_val, aexp_val)

    # 2. Model B
    acap_ord = float(ORDINAL_MAP.get(str(acap_val).lower(), acap_val if isinstance(acap_val, (int, float)) else 3))
    pcap_ord = float(ORDINAL_MAP.get(str(pcap_val).lower(), pcap_val if isinstance(pcap_val, (int, float)) else 3))
    aexp_ord = float(ORDINAL_MAP.get(str(aexp_val).lower(), aexp_val if isinstance(aexp_val, (int, float)) else 3))
    model_b_res = _calc_model_b(kloc, acap_ord, pcap_ord, aexp_ord, n_members)

    # 3. Analisis Beban Kerja
    workload_res = _calc_workload(n_members, n_tasks, db_path)

    # 4. Penanda Selisih Antar-Model
    comp_res = None
    if model_a_res.get("status") == "ready" and model_b_res.get("status") == "ready":
        comp_res = compare_models(
            model_a_res["adjusted_duration"],
            model_b_res["indicative_duration"],
        )

    response = {
        "model_a": model_a_res,
        "model_b": model_b_res,
        "workload": workload_res,
        "comparison": comp_res,
        "input_summary": {
            "n_members": n_members,
            "n_tasks": n_tasks,
            "kloc": kloc,
            "acap": acap_val,
            "pcap": pcap_val,
            "aexp": aexp_val,
        },
    }

    # Simpan hasil kalkulasi ke tabel estimations
    with connection.transaction(db_path) as conn:
        estimations_repo.save_estimation(conn, payload, response)

    return response


def _calc_model_a(
    n_members: int,
    n_tasks: int,
    kloc: float,
    acap: Any,
    pcap: Any,
    aexp: Any,
) -> dict[str, Any]:
    """Kalkulasi internal untuk Model A."""
    if not MODEL_A_PATH.exists():
        return {
            "status": "untrained",
            "message": "Model A belum dilatih. Jalankan python -m app.cli train-models.",
        }
    bundle = joblib.load(MODEL_A_PATH)
    base_dur, mae, warnings = predict_model_a(bundle, n_members, n_tasks, kloc)
    multipliers = load_cocomo_multipliers()
    adj = calculate_adjustment_factor(acap, pcap, aexp, multipliers)
    adj_dur = max(0.1, round(base_dur * adj["factor"], 2))

    return {
        "status": "ready",
        "base_duration": base_dur,
        "adjustment_factor": adj["factor"],
        "adjusted_duration": adj_dur,
        "mae": mae,
        "range": [max(0.1, round(adj_dur - mae, 2)), round(adj_dur + mae, 2)],
        "warnings": warnings,
    }


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


def _calc_workload(
    n_members: int,
    n_tasks: int,
    db_path: str | Path | None,
) -> dict[str, Any]:
    """Menghitung beban kerja berdasarkan sebaran rasio data latih."""
    dist: list[float] = []
    try:
        with connection.transaction(db_path) as conn:
            rows = training_rows_repo.list_training_rows(conn, included_only=True)
            for r in rows:
                if r.get("n_contributors") and r.get("n_work_items"):
                    dist.append(float(r["n_work_items"]) / float(r["n_contributors"]))
    except Exception:
        pass
    return analyze_workload(n_members, n_tasks, dist if dist else None)
