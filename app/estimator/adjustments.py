"""Modul penyesuaian level kapabilitas tim (skenario COCOMO) pada Model A."""
from __future__ import annotations

from typing import Any
from app.estimator.nasa93 import ORDINAL_MAP, interpolate_multiplier


def average_member_levels(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Menghitung rata-rata level kapabilitas (acap, pcap, aexp) dari daftar anggota."""
    if not members:
        return {
            "n_members": 1,
            "avg_acap_ord": 3.0,
            "avg_pcap_ord": 3.0,
            "avg_aexp_ord": 3.0,
        }

    total_acap = sum(float(ORDINAL_MAP.get(m.get("acap", "nominal"), 3)) for m in members)
    total_pcap = sum(float(ORDINAL_MAP.get(m.get("pcap", "nominal"), 3)) for m in members)
    total_aexp = sum(float(ORDINAL_MAP.get(m.get("aexp", "nominal"), 3)) for m in members)
    count = len(members)

    return {
        "n_members": count,
        "avg_acap_ord": round(total_acap / count, 2),
        "avg_pcap_ord": round(total_pcap / count, 2),
        "avg_aexp_ord": round(total_aexp / count, 2),
    }


def calculate_adjustment_factor(
    acap_val: float | str,
    pcap_val: float | str,
    aexp_val: float | str,
    multipliers: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Menghitung faktor pengali penyesuaian durasi berdasarkan level tim."""
    m_acap = interpolate_multiplier("acap", acap_val, multipliers)
    m_pcap = interpolate_multiplier("pcap", pcap_val, multipliers)
    m_aexp = interpolate_multiplier("aexp", aexp_val, multipliers)

    factor = round(m_acap * m_pcap * m_aexp, 3)
    return {
        "factor": factor,
        "m_acap": m_acap,
        "m_pcap": m_pcap,
        "m_aexp": m_aexp,
    }
