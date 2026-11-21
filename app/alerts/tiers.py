"""Ambang batas dan tier kekuatan alert bawaan (modul murni)."""
from __future__ import annotations

from typing import Any

DEFAULT_TIERS: dict[str, dict[str, Any]] = {
    "sentimen_turun": {
        "min_comments": 10,
        "lemah": 0.10,
        "sedang": 0.15,
        "kuat": 0.25,
    },
    "lonjakan_negatif": {
        "min_negative": 3,
        "lemah": 1.5,
        "sedang": 2.0,
        "kuat": 3.0,
    },
    "rilis_bermasalah": {
        "min_comments": 8,
        "days_window": 3,
        "lemah": 0.10,
        "sedang": 0.20,
        "kuat": 0.30,
    },
    "kata_kunci": {
        "lemah": 2,
        "sedang": 3,
        "kuat": 5,
    },
}


def determine_strength(
    value: float | int,
    lemah_val: float | int,
    sedang_val: float | int,
    kuat_val: float | int,
) -> str | None:
    """Menentukan tingkat kekuatan alert (lemah/sedang/kuat) dari nilai terukur."""
    if value >= kuat_val:
        return "kuat"
    if value >= sedang_val:
        return "sedang"
    if value >= lemah_val:
        return "lemah"
    return None
