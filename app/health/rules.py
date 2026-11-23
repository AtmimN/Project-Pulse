"""Aturan penentuan status kesehatan repositori (modul logika murni).

Modul ini independen dan murni memproses kalkulasi indikator tanpa framework eksternal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Batas nilai ambang (thresholds)
SPEED_RED_THRESHOLD: float = 90.0
SPEED_YELLOW_THRESHOLD: float = 75.0

WORKLOAD_RED_THRESHOLD: float = 90.0
WORKLOAD_YELLOW_THRESHOLD: float = 75.0

SENTIMENT_RED_THRESHOLD: float = -0.10
SENTIMENT_YELLOW_THRESHOLD: float = 0.10


@dataclass(frozen=True)
class HealthDimension:
    """Representasi satu dimensi evaluasi kesehatan repositori."""

    name: str
    status: str  # 'merah', 'kuning', 'hijau', 'abu-abu'
    reason: str
    value_display: str


def evaluate_speed(
    percentile: float | None,
    is_elapsed: bool = False,
    months_val: float | None = None,
) -> HealthDimension:
    """Mengevaluasi dimensi kecepatan (persentil durasi atau lama berjalan)."""
    if percentile is None or months_val is None:
        return HealthDimension(
            name="kecepatan",
            status="abu-abu",
            reason="Data snapshot durasi atau commit pertama tidak tersedia.",
            value_display="Tidak ada data",
        )

    context = "lama berjalan" if is_elapsed else "durasi sampai rilis stabil pertama"
    val_disp = f"{months_val:.1f} bln (persentil {percentile:.0f}%)"

    if percentile >= SPEED_RED_THRESHOLD:
        status = "merah"
        reason = (
            f"Tinggi ({percentile:.0f}%): {context} ({months_val:.1f} bulan) "
            f"berada di persentil >= {SPEED_RED_THRESHOLD:.0f}% repositori data latih."
        )
    elif percentile >= SPEED_YELLOW_THRESHOLD:
        status = "kuning"
        reason = (
            f"Sedang ({percentile:.0f}%): {context} ({months_val:.1f} bulan) "
            f"berada di persentil {SPEED_YELLOW_THRESHOLD:.0f}–{SPEED_RED_THRESHOLD:.0f}% repositori data latih."
        )
    else:
        status = "hijau"
        reason = (
            f"Normal ({percentile:.0f}%): {context} ({months_val:.1f} bulan) "
            f"di bawah persentil {SPEED_YELLOW_THRESHOLD:.0f}% repositori data latih."
        )

    return HealthDimension(
        name="kecepatan",
        status=status,
        reason=reason,
        value_display=val_disp,
    )


def evaluate_workload(
    percentile: float | None,
    tasks_per_member: float | None = None,
) -> HealthDimension:
    """Mengevaluasi dimensi beban per kontributor (rasio tugas terhadap kontributor)."""
    if percentile is None or tasks_per_member is None:
        return HealthDimension(
            name="beban",
            status="abu-abu",
            reason="Data tugas atau kontributor snapshot terkini tidak tersedia.",
            value_display="Tidak ada data",
        )

    val_disp = f"{tasks_per_member:.1f} tugas/kontributor (persentil {percentile:.0f}%)"

    if percentile >= WORKLOAD_RED_THRESHOLD:
        status = "merah"
        reason = (
            f"Sangat tinggi ({percentile:.0f}%): Beban {tasks_per_member:.1f} tugas/kontributor "
            f"berada di persentil >= {WORKLOAD_RED_THRESHOLD:.0f}% repositori data latih."
        )
    elif percentile >= WORKLOAD_YELLOW_THRESHOLD:
        status = "kuning"
        reason = (
            f"Tinggi ({percentile:.0f}%): Beban {tasks_per_member:.1f} tugas/kontributor "
            f"berada di persentil {WORKLOAD_YELLOW_THRESHOLD:.0f}–{WORKLOAD_RED_THRESHOLD:.0f}% repositori data latih."
        )
    else:
        status = "hijau"
        reason = (
            f"Normal ({percentile:.0f}%): Beban {tasks_per_member:.1f} tugas/kontributor "
            f"di bawah persentil {WORKLOAD_YELLOW_THRESHOLD:.0f}% repositori data latih."
        )

    return HealthDimension(
        name="beban",
        status=status,
        reason=reason,
        value_display=val_disp,
    )


def evaluate_mood(
    sentiment_index: float | None,
    comments_count: int,
    min_comments: int = 10,
    has_strong_alert_14d: bool = False,
    has_medium_alert_14d: bool = False,
) -> HealthDimension:
    """Mengevaluasi dimensi suasana (indeks sentimen 30 hari dan alert 14 hari terakhir)."""
    if sentiment_index is None or comments_count < min_comments:
        return HealthDimension(
            name="suasana",
            status="abu-abu",
            reason=f"Data komentar 30 hari belum cukup (n = {comments_count} komentar, minimal {min_comments}).",
            value_display=f"Data belum cukup (n = {comments_count})",
        )

    val_disp = f"Indeks: {sentiment_index:+.2f} ({comments_count} komentar)"

    if sentiment_index < SENTIMENT_RED_THRESHOLD or has_strong_alert_14d:
        status = "merah"
        reasons = []
        if sentiment_index < SENTIMENT_RED_THRESHOLD:
            reasons.append(f"indeks sentimen 30 hari ({sentiment_index:+.2f}) < {SENTIMENT_RED_THRESHOLD:.2f}")
        if has_strong_alert_14d:
            reasons.append("terdapat alert tingkat 'kuat' dalam 14 hari terakhir")
        reason = f"Perlu perhatian: {'; '.join(reasons)}."
    elif sentiment_index < SENTIMENT_YELLOW_THRESHOLD or has_medium_alert_14d:
        status = "kuning"
        reasons = []
        if sentiment_index < SENTIMENT_YELLOW_THRESHOLD:
            reasons.append(f"indeks sentimen 30 hari ({sentiment_index:+.2f}) < {SENTIMENT_YELLOW_THRESHOLD:.2f}")
        if has_medium_alert_14d:
            reasons.append("terdapat alert tingkat 'sedang' dalam 14 hari terakhir")
        reason = f"Waspada: {'; '.join(reasons)}."
    else:
        status = "hijau"
        reason = (
            f"Positif: indeks sentimen 30 hari ({sentiment_index:+.2f}) >= {SENTIMENT_YELLOW_THRESHOLD:.2f} "
            "dan tidak ada alert sedang/kuat dalam 14 hari terakhir."
        )

    return HealthDimension(
        name="suasana",
        status=status,
        reason=reason,
        value_display=val_disp,
    )


def evaluate_overall(dimensions: list[HealthDimension]) -> tuple[str, str]:
    """Mengevaluasi status ringkasan keseluruhan dari daftar dimensi."""
    available = [d for d in dimensions if d.status != "abu-abu"]
    if not available:
        return "abu-abu", "Tidak ada dimensi yang memiliki data cukup untuk dievaluasi."

    reds = [d for d in dimensions if d.status == "merah"]
    if reds:
        names = ", ".join(d.name for d in reds)
        return "merah", f"Terdapat dimensi kritis ({names}) yang memerlukan perhatian segera."

    yellows = [d for d in dimensions if d.status == "kuning"]
    if yellows:
        names = ", ".join(d.name for d in yellows)
        return "kuning", f"Terdapat dimensi ({names}) dalam rentang kewaspadaan."

    return "hijau", "Seluruh dimensi yang tersedia berada dalam kondisi normal/baik."
