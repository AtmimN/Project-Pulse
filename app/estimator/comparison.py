"""Modul penanda selisih antar hasil Model A dan Model B."""
from __future__ import annotations

from typing import Any
from app import config


def compare_models(duration_a: float, duration_b: float) -> dict[str, Any]:
    """Menghitung rasio selisih antar model dan memberi penanda bila berselisih jauh."""
    val_min = min(duration_a, duration_b)
    val_max = max(duration_a, duration_b)

    if val_min <= 0:
        ratio = 1.0
    else:
        ratio = round(val_max / val_min, 2)

    threshold = config.COMPARISON_FLAG_RATIO
    is_flagged = bool(ratio > threshold)

    if is_flagged:
        message = (
            f"Kedua model berselisih jauh (rasio {ratio}x > {threshold}x); "
            "perlakukan kedua hasil sebagai indikatif."
        )
    else:
        message = f"Kedua model berada dalam rentang estimasi yang selaras (rasio {ratio}x)."

    return {
        "ratio": ratio,
        "threshold": threshold,
        "is_flagged": is_flagged,
        "message": message,
    }
