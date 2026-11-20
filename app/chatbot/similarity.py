"""Modul perhitungan kemiripan teks (Jaccard, Fuzzy, Cakupan)."""
from __future__ import annotations

from difflib import SequenceMatcher

# Bobot metrik kemiripan kata (total = 1.0)
BOBOT_JACCARD: float = 0.4
BOBOT_FUZZY: float = 0.3
BOBOT_CAKUPAN: float = 0.3


def similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Menghitung skor kemiripan 0..1 antara token pesan dan token pola."""
    if not tokens_a or not tokens_b:
        return 0.0

    set_a = set(tokens_a)
    set_b = set(tokens_b)

    # 1. Jaccard similarity
    jaccard = len(set_a & set_b) / len(set_a | set_b)

    # 2. Fuzzy similarity (SequenceMatcher)
    fuzzy = SequenceMatcher(None, " ".join(tokens_a), " ".join(tokens_b)).ratio()

    # 3. Cakupan kata pola pada input
    cakupan = len(set_a & set_b) / len(set_b)

    skor = (BOBOT_JACCARD * jaccard) + (BOBOT_FUZZY * fuzzy) + (BOBOT_CAKUPAN * cakupan)
    return round(skor, 4)
