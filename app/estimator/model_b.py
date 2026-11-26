"""Model B: Regresi Linear estimasi usaha person-bulan dari dataset NASA93 COCOMO81."""
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
from sklearn.model_selection import KFold, train_test_split

from app import config

MODEL_B_PATH: Path = config.BASE_DIR / "models" / "model_b.joblib"
METRICS_B_PATH: Path = config.BASE_DIR / "models" / "metrics_b.json"


def _eval_model_b_cv(X: np.ndarray, y_log: np.ndarray, y_orig: np.ndarray) -> tuple[float, float]:
    """Menghitung MAE dan R2 validasi silang 5-lipatan pada skala asli."""
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_maes: list[float] = []
    cv_r2s: list[float] = []
    for tr_idx, val_idx in kf.split(X):
        m_cv = LinearRegression().fit(X[tr_idx], y_log[tr_idx])
        pred_orig_val = np.exp(m_cv.predict(X[val_idx]))
        cv_maes.append(float(mean_absolute_error(y_orig[val_idx], pred_orig_val)))
        cv_r2s.append(float(r2_score(y_orig[val_idx], pred_orig_val)))
    return round(float(np.mean(cv_maes)), 2), round(float(np.mean(cv_r2s)), 4)


def _build_metrics_b(
    final_model: LinearRegression, X_tr: np.ndarray, X_te: np.ndarray,
    y_te: np.ndarray, y_pred_te_log: np.ndarray, cv_mae: float, cv_r2: float,
    df_nasa: pd.DataFrame,
) -> dict[str, Any]:
    """Menyusun kamus metrik evaluasi Model B."""
    y_te_orig, y_pred_te_orig = np.exp(y_te), np.exp(y_pred_te_log)
    pairs = [
        {"actual": round(float(a), 1), "predicted": round(float(p), 1)}
        for a, p in zip(y_te_orig[:200], y_pred_te_orig[:200])
    ]
    return {
        "n_train": len(X_tr), "n_test": len(X_te),
        "test_r2_log": round(float(r2_score(y_te, y_pred_te_log)), 4),
        "test_r2_orig": round(float(r2_score(y_te_orig, y_pred_te_orig)), 4),
        "test_mae_person_months": round(float(mean_absolute_error(y_te_orig, y_pred_te_orig)), 2),
        "cv_mae": cv_mae, "cv_r2": cv_r2,
        "coefficients": [round(float(c), 4) for c in final_model.coef_],
        "intercept": round(float(final_model.intercept_), 4),
        "kloc_range": [float(df_nasa["equivphyskloc"].min()), float(df_nasa["equivphyskloc"].max())],
        "pairs": pairs, "trained_at": datetime.now().isoformat(),
    }


def train_model_b(df_nasa: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    """Melatih Model B berbasis log(KLOC) dan cost driver ordinal, lalu menyimpan metrik."""
    log_kloc = np.log(df_nasa["equivphyskloc"].to_numpy(dtype=float))
    acap = df_nasa["acap_ord"].to_numpy(dtype=float)
    pcap = df_nasa["pcap_ord"].to_numpy(dtype=float)
    aexp = df_nasa["aexp_ord"].to_numpy(dtype=float)

    X = np.column_stack([log_kloc, acap, pcap, aexp])
    y_log = np.log(df_nasa["act_effort"].to_numpy(dtype=float))
    y_orig = df_nasa["act_effort"].to_numpy(dtype=float)

    cv_mae, cv_r2 = _eval_model_b_cv(X, y_log, y_orig)
    X_tr, X_te, y_tr, y_te = train_test_split(X, y_log, test_size=0.2, random_state=42)
    final_model = LinearRegression().fit(X_tr, y_tr)
    y_pred_te_log = final_model.predict(X_te)

    metrics = _build_metrics_b(final_model, X_tr, X_te, y_te, y_pred_te_log, cv_mae, cv_r2, df_nasa)
    MODEL_B_PATH.parent.mkdir(parents=True, exist_ok=True)
    bundle = {"model": final_model, "metrics": metrics}
    joblib.dump(bundle, MODEL_B_PATH)
    with open(METRICS_B_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    return bundle, metrics


def predict_model_b(
    bundle: dict[str, Any],
    kloc: float,
    acap_ord: float,
    pcap_ord: float,
    aexp_ord: float,
    n_members: int,
) -> tuple[float, float, float, list[str]]:
    """Menghitung estimasi usaha (person-bulan) dan perkiraan durasi Model B."""
    model = bundle["model"]
    metrics = bundle["metrics"]
    warnings: list[str] = []

    # Validasi level rendah pada NASA93
    if acap_ord <= 2.0 or pcap_ord <= 2.0:
        warnings.append(
            "Pada NASA93, acap dan pcap hanya muncul pada level nominal hingga sangat tinggi, "
            "sehingga prediksi untuk level rendah tidak didukung data historis NASA93."
        )

    # Validasi rentang KLOC NASA93
    k_min, k_max = metrics.get("kloc_range", [1.9, 1150.0])
    if kloc < k_min or kloc > k_max:
        warnings.append(
            f"Ukuran KLOC ({kloc}) berada di luar rentang proyek NASA93 ({k_min} - {k_max} KLOC)."
        )

    X_in = np.array([[np.log(max(0.1, kloc)), acap_ord, pcap_ord, aexp_ord]], dtype=float)
    log_effort = float(model.predict(X_in)[0])
    effort = max(1.0, round(float(np.exp(log_effort)), 1))

    indicative_duration = max(0.1, round(effort / max(1, n_members), 2))
    mae = float(metrics.get("test_mae_person_months", 0.0))
    return effort, indicative_duration, mae, warnings
