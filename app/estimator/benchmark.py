"""Modul kalkulasi benchmark durasi dari repositori latih (logika murni)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np

from app import config

BENCHMARK_DURATION_PATH: Path = config.BASE_DIR / "models" / "benchmark_duration.json"


def calculate_duration_benchmark(durations: list[float] | np.ndarray) -> dict[str, Any]:
    """Menghitung metrik benchmark durasi: n, min, q1, median, q3, max."""
    if len(durations) == 0:
        return {
            "n": 0,
            "min": 0.0,
            "q1": 0.0,
            "median": 0.0,
            "q3": 0.0,
            "max": 0.0,
            "built_at": datetime.now().isoformat(),
        }

    arr = np.array(durations, dtype=float)
    return {
        "n": int(len(arr)),
        "min": round(float(np.min(arr)), 2),
        "q1": round(float(np.percentile(arr, 25)), 2),
        "median": round(float(np.median(arr)), 2),
        "q3": round(float(np.percentile(arr, 75)), 2),
        "max": round(float(np.max(arr)), 2),
        "built_at": datetime.now().isoformat(),
    }


def save_duration_benchmark(data: dict[str, Any], path: Path | None = None) -> None:
    """Menyimpan data benchmark durasi ke berkas JSON."""
    target_path = path or BENCHMARK_DURATION_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_duration_benchmark(path: Path | None = None) -> dict[str, Any] | None:
    """Memuat data benchmark durasi dari berkas JSON."""
    target_path = path or BENCHMARK_DURATION_PATH
    if not target_path.exists():
        return None
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
