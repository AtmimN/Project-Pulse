"""Pengujian modul estimasi proyek: Model A, Model B, NASA93, dan penyesuaian level."""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from app.estimator.adjustments import average_member_levels, calculate_adjustment_factor
from app.estimator.comparison import compare_models
from app.estimator.model_a import predict_model_a, train_model_a
from app.estimator.model_b import predict_model_b, train_model_b
from app.estimator.nasa93 import (
    interpolate_multiplier,
    load_cocomo_multipliers,
    load_nasa93_dataset,
)
from app.estimator.workload import analyze_workload


def test_nasa93_dataset_loader() -> None:
    """Memastikan dataset NASA93 terbaca dengan benar dan kolom ordinal terpetakan."""
    df = load_nasa93_dataset()
    assert len(df) == 93
    assert "equivphyskloc" in df.columns
    assert "act_effort" in df.columns
    assert "acap_ord" in df.columns
    assert "pcap_ord" in df.columns
    assert "aexp_ord" in df.columns

    # Verifikasi sebaran usaha median 252 dan maks 8211
    assert float(df["act_effort"].median()) == 252.0
    assert float(df["act_effort"].max()) == 8211.0


def test_cocomo_multipliers_and_interpolation() -> None:
    """Menguji pembacaan pengali COCOMO dan interpolasi linear nilai desimal."""
    mults = load_cocomo_multipliers()
    assert mults["acap"]["nominal"] == 1.00
    assert mults["pcap"]["nominal"] == 1.00
    assert mults["aexp"]["nominal"] == 1.00

    # Uji exact match
    m_nom = interpolate_multiplier("acap", "nominal", mults)
    assert m_nom == 1.00

    # Uji interpolasi level 2.5 (tengah antara level 2 rendah 1.19 dan level 3 nominal 1.00)
    m_interp = interpolate_multiplier("acap", 2.5, mults)
    assert m_interp == 1.095

    # Uji perhitungan faktor penyesuaian
    factor_res = calculate_adjustment_factor("nominal", "nominal", "nominal", mults)
    assert factor_res["factor"] == 1.0

    # Uji rata-rata kapabilitas anggota tim
    members = [
        {"acap": "sangat_rendah", "pcap": "rendah", "aexp": "nominal"},  # 1, 2, 3
        {"acap": "nominal", "pcap": "nominal", "aexp": "nominal"},        # 3, 3, 3
    ]
    avg = average_member_levels(members)
    assert avg["n_members"] == 2
    assert avg["avg_acap_ord"] == 2.0  # (1 + 3) / 2
    assert avg["avg_pcap_ord"] == 2.5  # (2 + 3) / 2
    assert avg["avg_aexp_ord"] == 3.0  # (3 + 3) / 2


def test_model_a_training_and_prediction(tmp_path: Path) -> None:
    """Menguji siklus pelatihan dan inferensi Model A pada data tiruan."""
    np.random.seed(42)
    n = 35
    contribs = np.random.randint(2, 50, size=n)
    tasks = np.random.randint(10, 500, size=n)
    kloc = np.random.uniform(1.0, 50.0, size=n)
    # Target sintetik
    duration = 0.2 * contribs + 0.05 * tasks + 0.3 * kloc + np.random.normal(0, 1, size=n)
    duration = np.maximum(1.0, duration)

    df_synth = pd.DataFrame({
        "n_contributors": contribs,
        "n_work_items": tasks,
        "kloc": kloc,
        "duration_months": duration,
    })

    bundle, metrics = train_model_a(df_synth)
    assert metrics["variant"] in ("raw", "log1p")
    assert metrics["test_mae"] > 0
    assert len(metrics["coefficients"]) == 3

    # Prediksi dalam rentang
    pred, mae, warns = predict_model_a(bundle, n_contributors=10, n_work_items=50, kloc=10.0)
    assert pred > 0
    assert len(warns) == 0

    # Prediksi di luar rentang
    _, _, warns_out = predict_model_a(bundle, n_contributors=200, n_work_items=50, kloc=10.0)
    assert len(warns_out) > 0


def test_model_b_training_and_prediction() -> None:
    """Menguji siklus pelatihan dan inferensi Model B dari NASA93."""
    df_nasa = load_nasa93_dataset()
    bundle, metrics = train_model_b(df_nasa)

    assert metrics["test_mae_person_months"] > 0
    assert metrics["test_r2_orig"] != 0

    # Prediksi untuk tim 5 orang
    effort, dur, mae, warns = predict_model_b(
        bundle=bundle,
        kloc=20.0,
        acap_ord=3.0,
        pcap_ord=3.0,
        aexp_ord=3.0,
        n_members=5,
    )
    assert effort > 0
    assert dur == round(effort / 5, 2)
    assert len(warns) == 0

    # Uji peringatan saat level kapabilitas programmer rendah
    _, _, _, warns_low = predict_model_b(
        bundle=bundle,
        kloc=20.0,
        acap_ord=1.0,
        pcap_ord=2.0,
        aexp_ord=3.0,
        n_members=5,
    )
    assert len(warns_low) > 0
    assert "level nominal hingga sangat tinggi" in warns_low[0]


def test_workload_and_comparison() -> None:
    """Menguji analisis beban kerja dan penanda rasio selisih antar model."""
    dist = [10.0, 20.0, 30.0, 40.0, 50.0]
    res_w = analyze_workload(n_members=2, n_tasks=120, training_workload_dist=dist)
    assert res_w["tasks_per_member"] == 60.0
    assert res_w["kategori"] == "sangat tinggi"

    # Penanda selisih antar-model
    res_comp_ok = compare_models(duration_a=10.0, duration_b=15.0)  # rasio 1.5x <= 2.0x
    assert res_comp_ok["is_flagged"] is False

    res_comp_flag = compare_models(duration_a=5.0, duration_b=15.0)  # rasio 3.0x > 2.0x
    assert res_comp_flag["is_flagged"] is True


def test_model_a_diagnostics_and_repeated_cv() -> None:
    """Menguji metrik M2-rev: RepeatedKFold, pembanding tebak-median, R2 out-of-fold, dan diagnostik."""
    np.random.seed(42)
    n = 25  # n_test akan 5 (< 10 -> holdout_reliable False)
    contribs = np.random.randint(2, 30, size=n)
    tasks = np.random.randint(10, 100, size=n)
    kloc = np.random.uniform(1.0, 20.0, size=n)
    duration = 0.5 * contribs + 0.1 * tasks + 0.4 * kloc + np.random.normal(0, 0.5, size=n)
    duration = np.maximum(1.0, duration)

    df_synth = pd.DataFrame({
        "n_contributors": contribs,
        "n_work_items": tasks,
        "kloc": kloc,
        "duration_months": duration,
    })

    _, metrics = train_model_a(df_synth)

    # 1. Metrik validasi silang & pembanding tebak-median
    assert "cv_mae" in metrics
    assert "cv_r2" in metrics
    assert "baseline_mae_cv" in metrics
    assert "improvement_pct" in metrics
    assert metrics["cv_mae"] > 0
    assert metrics["baseline_mae_cv"] > 0

    # 2. Holdout reliability (n_test = 5 < 10 -> False)
    assert metrics["n_test"] == 5
    assert metrics["holdout_reliable"] is False

    # 3. Diagnostik: Spearman correlation, kestabilan tanda, koefisien terstandar
    diag = metrics["diagnostics"]
    assert "spearman_correlation" in diag
    assert "duration_vs_n_contributors" in diag["spearman_correlation"]
    assert "duration_vs_n_work_items" in diag["spearman_correlation"]
    assert "duration_vs_kloc" in diag["spearman_correlation"]

    assert "sign_stability" in diag
    assert "n_contributors" in diag["sign_stability"]
    assert 0 <= diag["sign_stability"]["n_contributors"] <= 100

    assert "standardized_coefficients" in diag
    assert "n_contributors" in diag["standardized_coefficients"]

    assert "finding" in diag
    assert "kontributor kumulatif" in diag["finding"]


def test_model_a_determinism() -> None:
    """Memastikan pelatihan dua kali pada data identik menghasilkan metrik dan diagnostik sama persis."""
    np.random.seed(42)
    n = 30
    df_data = pd.DataFrame({
        "n_contributors": np.random.randint(2, 25, size=n),
        "n_work_items": np.random.randint(5, 80, size=n),
        "kloc": np.random.uniform(2.0, 15.0, size=n),
        "duration_months": np.random.uniform(2.0, 24.0, size=n),
    })

    _, metrics1 = train_model_a(df_data)
    _, metrics2 = train_model_a(df_data)

    assert metrics1["cv_mae"] == metrics2["cv_mae"]
    assert metrics1["cv_r2"] == metrics2["cv_r2"]
    assert metrics1["baseline_mae_cv"] == metrics2["baseline_mae_cv"]
    assert metrics1["coefficients"] == metrics2["coefficients"]
    assert metrics1["diagnostics"]["sign_stability"] == metrics2["diagnostics"]["sign_stability"]
    assert metrics1["diagnostics"]["standardized_coefficients"] == metrics2["diagnostics"]["standardized_coefficients"]


def test_code_inspection_no_sign_flipping() -> None:
    """Memastikan kode tidak membalik tanda koefisien atau membuang n_contributors (DoD M2-rev)."""
    model_a_code = Path("app/estimator/model_a.py").read_text(encoding="utf-8")
    assert "n_contributors" in model_a_code
    assert "-abs(" not in model_a_code
    assert "=-np.abs(" not in model_a_code
    assert "=-abs(" not in model_a_code
    assert "forced_negative" not in model_a_code


def test_model_a_pairs_out_of_fold_and_typical_duration() -> None:
    """Memastikan pairs diisi dari out-of-fold seluruh data latih dan typical_duration tersedia."""
    np.random.seed(123)
    n = 20
    df = pd.DataFrame({
        "n_contributors": np.random.randint(2, 20, size=n),
        "n_work_items": np.random.randint(10, 50, size=n),
        "kloc": np.random.uniform(2.0, 10.0, size=n),
        "duration_months": np.random.uniform(3.0, 18.0, size=n),
    })

    _, metrics = train_model_a(df)
    pairs = metrics.get("pairs", [])
    # pairs harus mencakup seluruh baris data latih (20 baris), bukan hanya hold-out
    assert len(pairs) == n
    assert "actual" in pairs[0] and "predicted" in pairs[0]

    # typical_duration harus memuat median, q25, q75, dan iqr
    assert "typical_duration" in metrics
    td = metrics["typical_duration"]
    assert "median" in td and "q25" in td and "q75" in td and "iqr" in td
    assert td["q25"] <= td["median"] <= td["q75"]
    assert round(td["q75"] - td["q25"], 2) == td["iqr"]


def test_diagnostics_finding_correlation_strength_tiers() -> None:
    """Memastikan diagnostics.finding menyesuaikan kekuatan korelasi (|rho| >= 0.5, 0.3-0.5, < 0.3)."""
    from app.estimator.model_a import _calculate_diagnostics
    features = ["n_contributors", "n_work_items", "kloc"]
    y_vals = [float(i) for i in range(1, 11)]
    work_items = [10 + i * 2 for i in range(10)]
    kloc_vals = [2.0 + i * 0.5 for i in range(10)]

    # 1. Korelasi kuat (|rho| >= 0.5, rho = 1.0)
    df_strong = pd.DataFrame({
        "n_contributors": list(range(1, 11)),
        "n_work_items": work_items,
        "kloc": kloc_vals,
        "duration_months": y_vals,
    })
    d_strong = _calculate_diagnostics(
        df_strong, df_strong[features].to_numpy(dtype=float), np.array(y_vals), features
    )
    assert "korelasi kuat" in d_strong["finding"]
    assert "kontributor kumulatif" in d_strong["finding"]
    assert "mencerminkan usia proyek" in d_strong["finding"]

    # 2. Korelasi sedang (0.3 <= |rho| < 0.5, rho ~ 0.44)
    df_mod = pd.DataFrame({
        "n_contributors": [1, 2, 3, 6, 10, 9, 8, 7, 5, 4],
        "n_work_items": work_items,
        "kloc": kloc_vals,
        "duration_months": y_vals,
    })
    d_mod = _calculate_diagnostics(
        df_mod, df_mod[features].to_numpy(dtype=float), np.array(y_vals), features
    )
    assert "korelasi sedang" in d_mod["finding"]
    assert "kontributor kumulatif" in d_mod["finding"]
    assert "mencerminkan usia proyek" in d_mod["finding"]

    # 3. Korelasi lemah (|rho| < 0.3, rho ~ 0.15)
    df_weak = pd.DataFrame({
        "n_contributors": [1, 10, 2, 9, 5, 6, 4, 7, 3, 8],
        "n_work_items": work_items,
        "kloc": kloc_vals,
        "duration_months": y_vals,
    })
    d_weak = _calculate_diagnostics(
        df_weak, df_weak[features].to_numpy(dtype=float), np.array(y_vals), features
    )
    assert "korelasi lemah" in d_weak["finding"]
    assert "jumlah kontributor tidak memprediksi durasi pada data ini" in d_weak["finding"]
    assert "mencerminkan usia proyek" not in d_weak["finding"]

