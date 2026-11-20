"""Modul analisis beban kerja tugas per anggota tim."""
from __future__ import annotations

import numpy as np


def analyze_workload(
    n_members: int,
    n_tasks: int,
    training_workload_dist: list[float] | None = None,
) -> dict[str, Any]:
    """Menganalisis rasio tugas per anggota terhadap sebaran data latih."""
    tasks_per_member = round(n_tasks / max(1, n_members), 2)

    # Distribusi acuan dari data latih (atau fallback representatif jika kosong)
    ref_dist = training_workload_dist if training_workload_dist else [5.0, 15.0, 30.0, 50.0, 100.0]
    p75 = float(np.percentile(ref_dist, 75))
    p90 = float(np.percentile(ref_dist, 90))

    if tasks_per_member > p90:
        kategori = "sangat tinggi"
        pesan = "Beban tugas per anggota sangat tinggi dibanding repositori latih (melebihi P90)."
    elif tasks_per_member > p75:
        kategori = "tinggi"
        pesan = "Beban tugas per anggota tinggi dibanding repositori latih (melebihi P75)."
    else:
        kategori = "wajar"
        pesan = "Beban tugas per anggota dalam rentang wajar repositori latih."

    # Hitung persentil eksak
    percentile_score = float((np.array(ref_dist) <= tasks_per_member).mean() * 100.0)

    return {
        "tasks_per_member": tasks_per_member,
        "percentile": round(percentile_score, 1),
        "kategori": kategori,
        "message": pesan,
        "p75": round(p75, 2),
        "p90": round(p90, 2),
    }
