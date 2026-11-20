"""Layanan pembaca data analitik dan metrik regresi untuk dashboard."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import config
from app.db import connection, training_rows_repo
from app.estimator.model_a import METRICS_A_PATH
from app.estimator.model_b import METRICS_B_PATH


def get_regression_a_data(db_path: str | Path | None = None) -> dict[str, Any] | None:
    """Mengambil metrik dan diagnostik Model A beserta jumlah data latih."""
    if not METRICS_A_PATH.exists():
        return None

    try:
        with open(METRICS_A_PATH, "r", encoding="utf-8") as f:
            metrics = json.load(f)
    except Exception:
        return None

    n_rows = 0
    try:
        with connection.transaction(db_path) as conn:
            rows = training_rows_repo.list_training_rows(conn, included_only=True)
            n_rows = len(rows)
    except Exception:
        n_rows = metrics.get("n_train", 0) + metrics.get("n_test", 0)

    metrics["n_training_rows"] = n_rows
    metrics["warning_insufficient"] = n_rows < config.MIN_TRAINING_ROWS
    return metrics


def get_regression_b_data() -> dict[str, Any] | None:
    """Mengambil metrik dan pasangan aktual-prediksi Model B NASA93."""
    if not METRICS_B_PATH.exists():
        return None

    try:
        with open(METRICS_B_PATH, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        return metrics
    except Exception:
        return None
