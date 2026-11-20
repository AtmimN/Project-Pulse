"""Model A: Regresi Linear estimasi durasi kalender dari data repositori GitHub."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import KFold, cross_val_score, train_test_split

from app import config

MODEL_A_PATH: Path = config.BASE_DIR / "models" / "model_a.joblib"
METRICS_A_PATH: Path = config.BASE_DIR / "models" / "metrics_a.json"


def _evaluate_cv(X: np.ndarray, y: np.ndarray, is_log: bool) -> tuple[float, float]:
    """Menghitung rata-rata MAE dan R2 validasi silang 5-lipatan pada skala asli."""
    kf = KFold(n_splits=min(5, len(X)), shuffle=True, random_state=42)
    maes: list[float] = []
    r2s: list[float] = []

    for train_idx, val_idx in kf.split(X):
        X_tr, X_val = X[train_idx], X[val_idx]
        y_tr, y_val = y[train_idx], y[val_idx]

        model = LinearRegression().fit(X_tr, y_tr)
        pred_val = model.predict(X_val)

        if is_log:
            pred_orig = np.expm1(pred_val)
            y_orig = np.expm1(y_val)
        else:
            pred_orig = pred_val
            y_orig = y_val

        maes.append(float(mean_absolute_error(y_orig, pred_orig)))
        r2s.append(float(r2_score(y_orig, pred_orig)))

    return float(np.mean(maes)), float(np.mean(r2s))


def train_model_a(df_train: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    """Melatih Model A, memilih varian terbaik (raw vs log1p), dan mencatat metrik."""
    features = ["n_contributors", "n_work_items", "kloc"]
    X_raw = df_train[features].to_numpy(dtype=float)
    y_raw = df_train["duration_months"].to_numpy(dtype=float)

    # Evaluasi varian (a) raw vs (b) log1p dengan validasi silang
    mae_raw_cv, r2_raw_cv = _evaluate_cv(X_raw, y_raw, is_log=False)
    X_log = np.log1p(X_raw)
    y_log = np.log1p(y_raw)
    mae_log_cv, r2_log_cv = _evaluate_cv(X_log, y_log, is_log=True)

    use_log = mae_log_cv < mae_raw_cv
    variant = "log1p" if use_log else "raw"
    X_chosen = X_log if use_log else X_raw
    y_chosen = y_log if use_log else y_raw

    # Split 80/20 data uji
    X_tr, X_te, y_tr, y_te, idx_tr, idx_te = train_test_split(
        X_chosen, y_chosen, df_train.index, test_size=0.2, random_state=42
    )
    final_model = LinearRegression().fit(X_tr, y_tr)
    y_pred_te = final_model.predict(X_te)

    # Kembalikan ke skala asli bulan
    y_te_orig = np.expm1(y_te) if use_log else y_te
    y_pred_orig = np.expm1(y_pred_te) if use_log else y_pred_te

    test_mae = float(mean_absolute_error(y_te_orig, y_pred_orig))
    test_r2 = float(r2_score(y_te_orig, y_pred_orig))

    # Catat pasangan aktual-prediksi hingga 200 baris
    pairs = [
        {"actual": round(float(a), 2), "predicted": round(float(p), 2)}
        for a, p in zip(y_te_orig[:200], y_pred_orig[:200])
    ]

    metrics = {
        "variant": variant,
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "test_r2": round(test_r2, 4),
        "test_mae": round(test_mae, 2),
        "cv_mae": round(mae_log_cv if use_log else mae_raw_cv, 2),
        "cv_r2": round(r2_log_cv if use_log else r2_raw_cv, 4),
        "cv_mae_raw": round(mae_raw_cv, 2),
        "cv_mae_log": round(mae_log_cv, 2),
        "coefficients": [round(float(c), 4) for c in final_model.coef_],
        "intercept": round(float(final_model.intercept_), 4),
        "feature_ranges": {
            col: [float(df_train[col].min()), float(df_train[col].max())]
            for col in features
        },
        "pairs": pairs,
        "trained_at": datetime.now().isoformat(),
    }

    # Simpan model dan metrik
    MODEL_A_PATH.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"model": final_model, "variant": variant, "metrics": metrics}
    joblib.dump(bundle, MODEL_A_PATH)
    with open(METRICS_A_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return bundle, metrics


def predict_model_a(
    bundle: dict[str, Any],
    n_contributors: int,
    n_work_items: int,
    kloc: float,
) -> tuple[float, float, list[str]]:
    """Menghitung estimasi durasi Model A beserta rentang MAE dan peringatan."""
    model = bundle["model"]
    variant = bundle["variant"]
    metrics = bundle["metrics"]
    warnings: list[str] = []

    # Validasi rentang input terhadap data latih
    ranges = metrics.get("feature_ranges", {})
    inputs = {
        "n_contributors": (n_contributors, "jumlah kontributor"),
        "n_work_items": (n_work_items, "jumlah tugas/issue"),
        "kloc": (kloc, "ukuran KLOC"),
    }
    for col, (val, label) in inputs.items():
        if col in ranges:
            c_min, c_max = ranges[col]
            if val < c_min or val > c_max:
                warnings.append(
                    f"Input {label} ({val}) berada di luar rentang data latih ({c_min} - {c_max})."
                )

    X_in = np.array([[n_contributors, n_work_items, kloc]], dtype=float)
    if variant == "log1p":
        pred_raw = model.predict(np.log1p(X_in))[0]
        duration = float(np.expm1(pred_raw))
    else:
        duration = float(model.predict(X_in)[0])

    duration_final = max(0.1, round(duration, 2))
    mae = float(metrics.get("test_mae", 0.0))
    return duration_final, mae, warnings
