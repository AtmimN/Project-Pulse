"""Modul praproses teks untuk chatbot rule-based ProjectPulse."""
from __future__ import annotations

import re

# Kamus pemetaan kata tidak baku menjadi kata baku (atau dihapus jika "")
NORMALISASI: dict[str, str] = {
    "gak": "tidak",
    "ga": "tidak",
    "nggak": "tidak",
    "enggak": "tidak",
    "tdk": "tidak",
    "gmn": "bagaimana",
    "bgmn": "bagaimana",
    "gimana": "bagaimana",
    "apaan": "apa",
    "ngapain": "apa",
    "bikin": "buat",
    "kerjanya": "tugas",
    "hi": "halo",
    "hai": "halo",
    "hello": "halo",
    "hallo": "halo",
    "makasih": "terima kasih",
    "terimakasih": "terima kasih",
    "thanks": "terima kasih",
    "thx": "terima kasih",
    "thank": "terima kasih",
    "software": "aplikasi",
    "kak": "",
    "bang": "",
    "dong": "",
    "sih": "",
    "deh": "",
    "nih": "",
    "ya": "",
    "yah": "",
    "dmn": "dimana",
    "brp": "berapa",
    "berapakah": "berapa",
    "yg": "yang",
    "dgn": "dengan",
    "utk": "untuk",
    "sy": "saya",
    "aku": "saya",
    "gue": "saya",
    "gw": "saya",
}

# Kata henti umum bahasa Indonesia yang aman dibuang
STOPWORDS: set[str] = {
    "yang", "di", "ke", "dari", "dan", "untuk", "dalam",
    "saja", "mau", "tolong", "boleh", "itu", "seorang",
    "adalah", "dengan", "sama", "bot", "aku", "saya", "kamu",
}


def preprocess(teks: str) -> list[str]:
    """Mengubah teks mentah menjadi daftar token kata yang dinormalisasi."""
    teks = teks.lower()
    teks = teks.replace("-", " ")
    teks = re.sub(r"[^a-z0-9\s]", " ", teks)

    tokens: list[str] = []
    for kata in teks.split():
        kata_normal = NORMALISASI.get(kata, kata)
        for k in kata_normal.split():
            if k and k not in STOPWORDS:
                tokens.append(k)
    return tokens
