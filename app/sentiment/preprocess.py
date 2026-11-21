"""Pembersihan dan prapemrosesan teks komentar GitHub (modul murni)."""
from __future__ import annotations

import re


def _strip_markdown_and_code(text: str) -> str:
    """Menghapus blok kode, kode sebaris, gambar, kutipan, dan URL."""
    # Hapus blok kode ```...```
    text = re.sub(r"```[\s\S]*?```", " ", text)
    # Hapus kode sebaris `...`
    text = re.sub(r"`[^`\n]*?`", " ", text)
    # Hapus sintaks gambar ![...](...)
    text = re.sub(r"!\[.*?\]\(.*?\)", " ", text)
    # Ganti tautan markdown [...](...) dengan teks di dalam kurung siku
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # Hapus URL http/https
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    # Hapus baris kutipan balasan (diawali >)
    text = re.sub(r"^\s*>.*$", " ", text, flags=re.MULTILINE)
    return text


def clean_text(text: str | None) -> str:
    """Membersihkan teks komentar GitHub dari kode, markup, mention, dan HTML."""
    if not text or not isinstance(text, str):
        return ""

    text = _strip_markdown_and_code(text)
    # Hapus mention pengguna (@username)
    text = re.sub(r"@[\w\-]+", " ", text)
    # Hapus tag HTML
    text = re.sub(r"<[^>]+>", " ", text)
    # Rapikan spasi berlebih
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned
