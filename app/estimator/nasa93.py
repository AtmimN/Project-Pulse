"""Modul pemrosesan dan pembacaan dataset NASA93 COCOMO81."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import pandas as pd

from app import config

DEFAULT_NASA93_PATH: Path = config.BASE_DIR / "data" / "nasa93" / "nasa93.arff"
DEFAULT_MULTIPLIERS_PATH: Path = config.BASE_DIR / "data" / "nasa93" / "cocomo_multipliers.json"

# Pemetaan peringkat diskret ke skala ordinal 1..5
ORDINAL_MAP: dict[str, int] = {
    "vl": 1,
    "l": 2,
    "n": 3,
    "h": 4,
    "vh": 5,
    "xh": 6,
    "sangat_rendah": 1,
    "rendah": 2,
    "nominal": 3,
    "tinggi": 4,
    "sangat_tinggi": 5,
}

ORDINAL_TO_NAME: dict[int, str] = {
    1: "sangat_rendah",
    2: "rendah",
    3: "nominal",
    4: "tinggi",
    5: "sangat_tinggi",
}


def load_nasa93_dataset(file_path: str | Path | None = None) -> pd.DataFrame:
    """Membaca berkas NASA93 (ARFF atau CSV) menjadi DataFrame terstruktur."""
    target_path = Path(file_path or DEFAULT_NASA93_PATH)
    if not target_path.exists():
        raise FileNotFoundError(f"Berkas dataset NASA93 tidak ditemukan pada {target_path}")

    if target_path.suffix.lower() == ".arff":
        from scipy.io import arff
        data, _ = arff.loadarff(str(target_path))
        df = pd.DataFrame(data)
    else:
        df = pd.read_csv(target_path)

    # Decode bytes kolom string jika dari arff
    for col in df.select_dtypes(include=["object"]).columns:
        if len(df) > 0 and isinstance(df[col].iloc[0], bytes):
            df[col] = df[col].str.decode("utf-8")

    # Validasi keberadaan kolom esensial
    required_cols = ["equivphyskloc", "act_effort", "acap", "pcap", "aexp"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Kolom wajib '{col}' tidak ditemukan dalam dataset NASA93.")

    # Konversi kolom kategori biaya menjadi skala ordinal numerik
    for col in ["acap", "pcap", "aexp"]:
        df[f"{col}_ord"] = df[col].astype(str).str.lower().map(ORDINAL_MAP).fillna(3)

    return df


def load_cocomo_multipliers(file_path: str | Path | None = None) -> dict[str, dict[str, float]]:
    """Membaca tabel pengali COCOMO dari berkas JSON."""
    target_path = Path(file_path or DEFAULT_MULTIPLIERS_PATH)
    if not target_path.exists():
        raise FileNotFoundError(
            f"Tabel pengali COCOMO tidak ditemukan. Sediakan berkas {target_path}."
        )

    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for driver in ["acap", "pcap", "aexp"]:
        if driver not in data:
            raise ValueError(f"Pengali untuk '{driver}' tidak lengkap pada berkas JSON.")
    return data


def interpolate_multiplier(
    driver: str,
    level_val: float | str,
    multipliers: dict[str, dict[str, float]],
) -> float:
    """Menghitung pengali COCOMO dengan interpolasi linear antar level bertetangga."""
    driver_multipliers = multipliers.get(driver, {})
    if isinstance(level_val, str):
        level_clean = level_val.strip().lower()
        if level_clean in driver_multipliers:
            return float(driver_multipliers[level_clean])
        ord_val = float(ORDINAL_MAP.get(level_clean, 3))
    else:
        ord_val = float(level_val)

    if ord_val <= 1.0:
        return float(driver_multipliers["sangat_rendah"])
    if ord_val >= 5.0:
        return float(driver_multipliers["sangat_tinggi"])

    lower_idx = int(ord_val)
    upper_idx = lower_idx + 1

    lower_name = ORDINAL_TO_NAME[lower_idx]
    upper_name = ORDINAL_TO_NAME[upper_idx]

    m_low = float(driver_multipliers[lower_name])
    m_high = float(driver_multipliers[upper_name])

    fraction = ord_val - lower_idx
    return round(m_low + fraction * (m_high - m_low), 4)
