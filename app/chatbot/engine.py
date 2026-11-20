"""Mesin inferensi chatbot rule-based murni untuk ProjectPulse."""
from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from app.chatbot.preprocessing import preprocess
from app.chatbot.similarity import similarity

DEFAULT_INTENTS_PATH: Path = Path(__file__).resolve().parent / "data" / "intents.json"


def load_intents(file_path: str | Path | None = None) -> dict[str, Any]:
    """Membaca dan memvalidasi berkas konfigurasi intent JSON."""
    target_path = Path(file_path or DEFAULT_INTENTS_PATH)
    with open(target_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data.get("intents"), list):
        raise ValueError("Berkas intent harus memiliki kunci 'intents' berupa list.")
    if not data.get("fallback"):
        raise ValueError("Berkas intent harus memiliki daftar 'fallback'.")
    return data


class ChatbotEngine:
    """Mesin inferensi pencocokan aturan intent statis dan dinamis."""

    def __init__(
        self,
        intents_data: dict[str, Any],
        threshold: float = 0.45,
        handlers: dict[str, Callable[[str, Any], str]] | None = None,
        provider: Any = None,
    ) -> None:
        self.data = intents_data
        self.threshold = threshold
        self.handlers = handlers or {}
        self.provider = provider

        # Pola dipraproses saat inisialisasi agar inferensi cepat
        self._patterns: list[tuple[str, str, list[str]]] = []
        self._responses: dict[str, list[str]] = {}
        self._intent_handlers: dict[str, str] = {}

        for intent in self.data.get("intents", []):
            tag = intent["tag"]
            self._responses[tag] = intent.get("responses", [])
            if intent.get("handler"):
                self._intent_handlers[tag] = intent["handler"]
            for pola in intent.get("patterns", []):
                self._patterns.append((tag, pola, preprocess(pola)))

    def explain(self, pesan: str, top: int = 3) -> list[dict[str, Any]]:
        """Mengembalikan daftar kandidat intent dengan skor kemiripan tertinggi."""
        tokens = preprocess(pesan)
        if not tokens:
            return []

        terbaik: dict[str, dict[str, Any]] = {}
        for tag, pola, pola_tokens in self._patterns:
            skor = similarity(tokens, pola_tokens)
            if tag not in terbaik or skor > terbaik[tag]["score"]:
                terbaik[tag] = {
                    "intent": tag,
                    "pattern": pola,
                    "score": round(skor, 3),
                }

        kandidat = sorted(terbaik.values(), key=lambda x: x["score"], reverse=True)
        return kandidat[:top]

    def classify(self, pesan: str) -> tuple[str | None, float]:
        """Mengidentifikasi intent dari pesan pengguna berdasarkan ambang batas."""
        kandidat = self.explain(pesan, top=1)
        if not kandidat:
            return None, 0.0

        terpilih = kandidat[0]
        if terpilih["score"] < self.threshold:
            return None, terpilih["score"]

        return terpilih["intent"], terpilih["score"]

    def _isi_placeholder(self, teks: str) -> str:
        """Mengganti variabel dinamis waktu, tanggal, dan nama bot."""
        sekarang = datetime.now()
        teks = teks.replace("{waktu}", sekarang.strftime("%H:%M"))
        teks = teks.replace("{tanggal}", sekarang.strftime("%d-%m-%Y"))
        teks = teks.replace("{nama_bot}", self.data.get("bot_name", "PM-Bot"))
        return teks

    def reply(self, pesan: str) -> dict[str, Any]:
        """Menghasilkan jawaban balasan chatbot untuk pesan pengguna."""
        if not pesan or not pesan.strip():
            return {
                "reply": "Pesannya masih kosong. Silakan ketik pertanyaan Anda.",
                "intent": None,
                "score": 0.0,
            }

        tag, skor = self.classify(pesan)
        if tag is None:
            jawaban_mentah = random.choice(self.data["fallback"])
            return {
                "reply": self._isi_placeholder(jawaban_mentah),
                "intent": None,
                "score": skor,
            }

        # Cek apakah intent ini memiliki handler dinamis
        handler_name = self._intent_handlers.get(tag)
        if handler_name and handler_name in self.handlers:
            handler_func = self.handlers[handler_name]
            reply_text = handler_func(pesan, self.provider)
            return {
                "reply": reply_text,
                "intent": tag,
                "score": skor,
            }

        # Intent statis standar
        responses = self._responses.get(tag, self.data["fallback"])
        jawaban_mentah = random.choice(responses)
        return {
            "reply": self._isi_placeholder(jawaban_mentah),
            "intent": tag,
            "score": skor,
        }
