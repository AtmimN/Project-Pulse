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


def train_model_b(df_nasa: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    """Melatih Model B berbasis log(KLOC) dan cost driver ordinal, lalu menyimpan metrik."""
    # Fitur: log(KLOC), acap_ord, pcap_ord, aexp_ord
    log_kloc = np.log(df_nasa["equivphyskloc"].to_numpy(dtype=float))
    acap = df_nasa["acap_ord"].to_numpy(dtype=float)
    pcap = df_nasa["pcap_ord"].to_numpy(dtype=float)
    aexp = df_nasa["aexp_ord"].to_numpy(dtype=float)

    X = np.column_stack([log_kloc, acap, pcap, aexp])
    y_log = np.log(df_nasa["act_effort"].to_numpy(dtype=float))
    y_orig = df_nasa["act_effort"].to_numpy(dtype=float)

    # Validasi silang 5-lipatan
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_maes: list[float] = []
    cv_r2s: list[float] = []
    for tr_idx, val_idx in kf.split(X):
        m_cv = LinearRegression().fit(X[tr_idx], y_log[tr_idx])
        pred_orig_val = np.exp(m_cv.predict(X[val_idx]))
        cv_maes.append(float(mean_absolute_error(y_orig[val_idx], pred_orig_val)))
        cv_r2s.append(float(r2_score(y_orig[val_idx], pred_orig_val)))

    # Split 80/20 data uji
    X_tr, X_te, y_tr, y_te, idx_tr, idx_te = train_test_split(
        X, y_log, df_nasa.index, test_size=0.2, random_state=42
    )
    final_model = LinearRegression().fit(X_tr, y_tr)
    y_pred_te_log = final_model.predict(X_te)

    y_te_orig = np.exp(y_te)
    y_pred_te_orig = np.exp(y_pred_te_log)

    test_r2_log = float(r2_score(y_te, y_pred_te_log))
    test_r2_orig = float(r2_score(y_te_orig, y_pred_te_orig))
    test_mae_orig = float(mean_absolute_error(y_te_orig, y_pred_te_orig))

    pairs = [
        {"actual": round(float(a), 1), "predicted": round(float(p), 1)}
        for a, p in zip(y_te_orig[:200], y_pred_te_orig[:200])
    ]

    kloc_min = float(df_nasa["equivphyskloc"].min())
    kloc_max = float(df_nasa["equivphyskloc"].max())

    metrics = {
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "test_r2_log": round(test_r2_log, 4),
        "test_r2_orig": round(test_r2_orig, 4),
        "test_mae_person_months": round(test_mae_orig, 2),
        "cv_mae": round(float(np.mean(cv_maes)), 2),
        "cv_r2": round(float(np.mean(cv_r2s)), 4),
        "coefficients": [round(float(c), 4) for c in final_model.coef_],
        "intercept": round(float(final_model.intercept_), 4),
        "kloc_range": [kloc_min, kloc_max],
        "pairs": pairs,
        "trained_at": datetime.now().isoformat(),
    }

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
