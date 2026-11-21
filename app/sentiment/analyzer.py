"""Penganalisis sentimen berbasis VADER dengan penyesuaian leksikon teknis (modul murni)."""
from __future__ import annotations

from typing import Sequence
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from app import config
from app.sentiment.preprocess import clean_text


class VaderSentimentAnalyzer:
    """Penganalisis sentimen domain teknis berbasis VADER."""

    def __init__(
        self,
        neutral_words: Sequence[str] | None = None,
        pos_threshold: float = 0.05,
        neg_threshold: float = -0.05,
    ) -> None:
        self.pos_threshold = pos_threshold
        self.neg_threshold = neg_threshold
        self._analyzer = SentimentIntensityAnalyzer()

        # Terapkan valensi 0.0 pada kata-kata teknis agar tidak bias negatif
        words = neutral_words if neutral_words is not None else config.TECHNICAL_NEUTRAL_WORDS
        for word in words:
            self._analyzer.lexicon[word.lower()] = 0.0

    def analyze(self, text: str | None) -> tuple[float, str]:
        """Menganalisis teks dan mengembalikan (compound_score, sentiment_label)."""
        cleaned = clean_text(text)
        if not cleaned:
            return 0.0, "netral"

        scores = self._analyzer.polarity_scores(cleaned)
        compound = float(scores.get("compound", 0.0))

        if compound >= self.pos_threshold:
            label = "positif"
        elif compound <= self.neg_threshold:
            label = "negatif"
        else:
            label = "netral"

        return round(compound, 4), label
