"""Model A: Regresi Linear estimasi durasi kalender dari data repositori GitHub."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import RepeatedKFold, train_test_split

from app import config

MODEL_A_PATH: Path = config.BASE_DIR / "models" / "model_a.joblib"
METRICS_A_PATH: Path = config.BASE_DIR / "models" / "metrics_a.json"


def _evaluate_repeated_cv(
    X: np.ndarray,
    y: np.ndarray,
    is_log: bool,
    n_splits: int = 5,
    n_repeats: int = 20,
    random_state: int = 42,
) -> tuple[float, float, float, np.ndarray]:
    """Menghitung MAE, R2, baseline MAE, dan rata-rata prediksi out-of-fold skala asli."""
    n_samples = len(X)
    actual_splits = max(2, min(n_splits, n_samples))
    rkf = RepeatedKFold(n_splits=actual_splits, n_repeats=n_repeats, random_state=random_state)

    fold_maes: list[float] = []
    fold_baseline_maes: list[float] = []
    repeat_r2s: list[float] = []
    y_orig_all = np.expm1(y) if is_log else y
    oof_accum = np.zeros(n_samples, dtype=float)

    for r_idx in range(n_repeats):
        oof_preds = np.zeros(n_samples, dtype=float)
        split_gen = rkf.split(X)
        for _ in range(r_idx * actual_splits):
            next(split_gen)

        for _ in range(actual_splits):
            train_idx, val_idx = next(split_gen)
            model = LinearRegression().fit(X[train_idx], y[train_idx])
            pred_val = model.predict(X[val_idx])

            pred_orig = np.expm1(pred_val) if is_log else pred_val
            y_val_orig = np.expm1(y[val_idx]) if is_log else y[val_idx]
            y_tr_orig = np.expm1(y[train_idx]) if is_log else y[train_idx]

            oof_preds[val_idx] = pred_orig
            fold_maes.append(float(mean_absolute_error(y_val_orig, pred_orig)))

            med_tr = float(np.median(y_tr_orig))
            pred_base = np.full_like(y_val_orig, fill_value=med_tr)
            fold_baseline_maes.append(float(mean_absolute_error(y_val_orig, pred_base)))

        repeat_r2s.append(float(r2_score(y_orig_all, oof_preds)))
        oof_accum += oof_preds

    cv_mae = float(np.mean(fold_maes))
    cv_r2 = float(np.mean(repeat_r2s))
    baseline_mae_cv = float(np.mean(fold_baseline_maes))
    mean_oof_preds = oof_accum / float(n_repeats)
    return cv_mae, cv_r2, baseline_mae_cv, mean_oof_preds


def _calculate_diagnostics(
    df_train: pd.DataFrame,
    X_chosen: np.ndarray,
    y_chosen: np.ndarray,
    features: list[str],
) -> dict[str, Any]:
    """Menghitung korelasi Spearman, kestabilan tanda koefisien, dan koefisien terstandar."""
    y_raw = df_train["duration_months"].to_numpy(dtype=float)
    spearman_corr: dict[str, float] = {}
    for feat in features:
        val, _ = spearmanr(y_raw, df_train[feat].to_numpy(dtype=float))
        spearman_corr[f"duration_vs_{feat}"] = round(float(val), 4)

    for i in range(len(features)):
        for j in range(i + 1, len(features)):
            f1, f2 = features[i], features[j]
            c_val, _ = spearmanr(df_train[f1].to_numpy(dtype=float), df_train[f2].to_numpy(dtype=float))
            spearman_corr[f"{f1}_vs_{f2}"] = round(float(c_val), 4)

    rng = np.random.RandomState(42)
    n_samples = len(X_chosen)
    pos_counts = np.zeros(len(features), dtype=int)
    for _ in range(1000):
        idx = rng.choice(n_samples, size=n_samples, replace=True)
        boot_model = LinearRegression().fit(X_chosen[idx], y_chosen[idx])
        pos_counts += (boot_model.coef_ > 0).astype(int)

    sign_stability = {
        feat: round(float((pos_counts[k] / 1000.0) * 100), 1)
        for k, feat in enumerate(features)
    }

    mean_x = np.mean(X_chosen, axis=0)
    std_x = np.std(X_chosen, axis=0)
    std_x_safe = np.where(std_x == 0, 1.0, std_x)
    X_std = (X_chosen - mean_x) / std_x_safe
    std_model = LinearRegression().fit(X_std, y_chosen)
    standardized_coefs = {
        feat: round(float(std_model.coef_[k]), 4)
        for k, feat in enumerate(features)
    }

    rho_contrib = spearman_corr.get("duration_vs_n_contributors", 0.0)
    abs_rho = abs(rho_contrib)
    if abs_rho >= 0.5:
        finding = (
            f"korelasi kuat, \u03c1 = {rho_contrib:.2f}; durasi berkorelasi dengan kontributor kumulatif, "
            "ini mencerminkan usia proyek, bukan efek menambah anggota."
        )
    elif abs_rho >= 0.3:
        finding = (
            f"korelasi sedang, \u03c1 = {rho_contrib:.2f}; durasi berkorelasi dengan kontributor kumulatif, "
            "ini mencerminkan usia proyek, bukan efek menambah anggota."
        )
    else:
        finding = (
            f"korelasi lemah, \u03c1 = {rho_contrib:.2f}; "
            "jumlah kontributor tidak memprediksi durasi pada data ini"
        )
    return {
        "spearman_correlation": spearman_corr,
        "sign_stability": sign_stability,
        "standardized_coefficients": standardized_coefs,
        "finding": finding,
    }


def train_model_a(df_train: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
    """Melatih Model A, memilih varian terbaik (raw vs log1p), dan mencatat metrik diagnostik."""
    features = ["n_contributors", "n_work_items", "kloc"]
    X_raw = df_train[features].to_numpy(dtype=float)
    y_raw = df_train["duration_months"].to_numpy(dtype=float)

    mae_raw_cv, r2_raw_cv, base_raw_cv, oof_raw = _evaluate_repeated_cv(X_raw, y_raw, is_log=False)
    X_log = np.log1p(X_raw)
    y_log = np.log1p(y_raw)
    mae_log_cv, r2_log_cv, base_log_cv, oof_log = _evaluate_repeated_cv(X_log, y_log, is_log=True)

    use_log = mae_log_cv < mae_raw_cv
    variant = "log1p" if use_log else "raw"
    X_chosen = X_log if use_log else X_raw
    y_chosen = y_log if use_log else y_raw
    oof_chosen = oof_log if use_log else oof_raw

    cv_mae = mae_log_cv if use_log else mae_raw_cv
    cv_r2 = r2_log_cv if use_log else r2_raw_cv
    baseline_mae_cv = base_log_cv if use_log else base_raw_cv
    improvement_pct = round(((baseline_mae_cv - cv_mae) / baseline_mae_cv) * 100, 2) if baseline_mae_cv > 0 else 0.0

    X_tr, X_te, y_tr, y_te = train_test_split(
        X_chosen, y_chosen, test_size=0.2, random_state=42
    )
    holdout_reliable = bool(len(X_te) >= 10)
    final_model = LinearRegression().fit(X_tr, y_tr)
    y_pred_te = final_model.predict(X_te)

    y_te_orig = np.expm1(y_te) if use_log else y_te
    y_pred_orig = np.expm1(y_pred_te) if use_log else y_pred_te
    test_mae = float(mean_absolute_error(y_te_orig, y_pred_orig))
    test_r2 = float(r2_score(y_te_orig, y_pred_orig))

    diagnostics = _calculate_diagnostics(df_train, X_chosen, y_chosen, features)
    pairs = [
        {"actual": round(float(a), 2), "predicted": round(float(p), 2)}
        for a, p in zip(y_raw[:200], oof_chosen[:200])
    ]

    durations = df_train["duration_months"].to_numpy(dtype=float)
    q25 = round(float(np.percentile(durations, 25)), 2)
    q75 = round(float(np.percentile(durations, 75)), 2)
    typical_duration = {
        "median": round(float(np.median(durations)), 2),
        "q25": q25,
        "q75": q75,
        "iqr": round(float(q75 - q25), 2),
    }

    metrics = {
        "variant": variant,
        "n_train": len(X_tr),
        "n_test": len(X_te),
        "test_r2": round(test_r2, 4),
        "test_mae": round(test_mae, 2),
        "holdout_reliable": holdout_reliable,
        "cv_mae": round(cv_mae, 2),
        "cv_r2": round(cv_r2, 4),
        "cv_mae_raw": round(mae_raw_cv, 2),
        "cv_mae_log": round(mae_log_cv, 2),
        "baseline_mae_cv": round(baseline_mae_cv, 2),
        "improvement_pct": improvement_pct,
        "coefficients": [round(float(c), 4) for c in final_model.coef_],
        "intercept": round(float(final_model.intercept_), 4),
        "feature_ranges": {
            col: [float(df_train[col].min()), float(df_train[col].max())]
            for col in features
        },
        "diagnostics": diagnostics,
        "pairs": pairs,
        "typical_duration": typical_duration,
        "trained_at": datetime.now().isoformat(),
    }

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
    """Menghitung estimasi durasi Model A beserta rentang MAE validasi silang dan peringatan."""
    model = bundle["model"]
    variant = bundle["variant"]
    metrics = bundle["metrics"]
    warnings: list[str] = []

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
    mae = float(metrics.get("cv_mae", metrics.get("test_mae", 0.0)))
    return duration_final, mae, warnings
