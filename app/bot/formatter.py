"""Modul pemformat pesan teks untuk Bot Telegram (modul murni)."""
from __future__ import annotations

import html
from typing import Any

from app import config


def escape_text(text: str) -> str:
    """Meng-escape teks tak tepercaya (misal kutipan komentar) untuk keamanan tampilan."""
    return html.escape(text.strip())


def split_long_message(text: str, max_length: int = 4096) -> list[str]:
    """Memecah pesan panjang menjadi beberapa bagian <= 4096 karakter."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    lines = text.split("\n")
    current_chunk = ""

    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_length:
            if current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = ""
            while len(line) > max_length:
                chunks.append(line[:max_length])
                line = line[max_length:]
            current_chunk = line + "\n"
        else:
            current_chunk += line + "\n"

    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def format_start_message() -> str:
    """Menyusun pesan selamat datang dan pengenalan perintah bot."""
    return (
        "👋 Selamat datang di ProjectPulse Bot!\n\n"
        "Bot ini memantau sentimen komentar dan rilis repositori proyek open source pilihan Anda.\n\n"
        "Perintah yang tersedia:\n"
        "• /pantau [repo] — Tambah repositori ke daftar pantau Anda\n"
        "• /berhenti [repo|semua] — Hapus dari daftar pantau\n"
        "• /ringkasan [repo] — Lihat skor sentimen & metrik repositori\n"
        "• /bandingkan <repo1> <repo2> — Bandingkan dua repositori\n"
        "• /ambang [rendah|sedang|tinggi] — Atur sensitivitas alert\n"
        "• /bantuan — Tampilkan daftar bantuan perintah\n\n"
        f"Dashboard: {config.DASHBOARD_URL}"
    )


def format_help_message() -> str:
    """Menyusun pesan bantuan perintah bot."""
    return (
        "📖 Panduan Perintah ProjectPulse Bot:\n\n"
        "• /pantau <nama> — Memantau repositori (misal: /pantau planka)\n"
        "• /pantau — Melihat daftar repositori yang bisa dipantau\n"
        "• /berhenti <nama> — Berhenti memantau repositori tertentu\n"
        "• /berhenti semua — Mengosongkan seluruh watchlist Anda\n"
        "• /berhenti — Melihat repositori yang sedang dipantau\n"
        "• /ringkasan <nama> — Skor sentimen & tren 7h vs 30h repositori\n"
        "• /ringkasan — Ringkasan seluruh repositori di watchlist Anda\n"
        "• /bandingkan <repo1> <repo2> — Komparasi metrik sentimen 2 repo\n"
        "• /ambang [rendah|sedang|tinggi] — Kelola sensitivitas notifikasi\n"
        f"\nKunjungi dashboard: {config.DASHBOARD_URL}"
    )


def format_repo_summary(summary: dict[str, Any]) -> str:
    """Menyusun teks ringkasan untuk satu repositori."""
    repo = summary.get("repo", {})
    name = repo.get("full_name", "Unknown") if repo else "Unknown"
    if not summary.get("has_data"):
        return f"📊 {name}\nBelum ada data komentar yang tersimpan untuk repositori ini."

    rel = summary.get("latest_release")
    rel_txt = f"{rel['tag']} ({rel['published_at'][:10]})" if rel else "Belum ada rilis"
    upd_txt = summary.get("last_updated") or "Belum tersedia"
    c30 = summary.get("comments_30d", 0)

    if c30 < config.MIN_COMMENTS_FOR_SUMMARY:
        return (
            f"📊 Ringkasan Repositori: {name}\n"
            f"• Data belum cukup (n = {c30} komentar dalam 30 hari)\n"
            f"• Komentar 30 Hari: {c30} (Total tersimpan: {summary['total_comments']})\n"
            f"• Rilis Terbaru: {rel_txt}\n"
            f"• Terakhir Diperbarui: {upd_txt}"
        )

    trend_sym = {"naik": "↗ (naik)", "turun": "↘ (turun)", "stabil": "→ (stabil)"}.get(summary["trend"], "→")
    c7 = summary.get("comments_7d", 0)
    note_7d = f" ({c7} komentar) (sedikit data)" if c7 < config.MIN_COMMENTS_FOR_SUMMARY else f" ({c7} komentar)"

    return (
        f"📊 Ringkasan Repositori: {name}\n"
        f"• Indeks Sentimen 7 Hari: {summary['index_7d']}{note_7d} {trend_sym}\n"
        f"  (vs 30 hari sebelumnya: {summary['index_prev']})\n"
        f"• Sebaran Sentimen 30 Hari: Positif {summary['pct_positive']}%, Netral {summary['pct_neutral']}%, Negatif {summary['pct_negative']}%\n"
        f"• Komentar 30 Hari: {c30} (Total tersimpan: {summary['total_comments']})\n"
        f"• Rilis Terbaru: {rel_txt}\n"
        f"• Terakhir Diperbarui: {upd_txt}"
    )


def format_comparison(data: dict[str, Any]) -> str:
    """Menyusun format tampilan komparasi dua repositori."""
    s1 = data["repo1_summary"]
    s2 = data["repo2_summary"]
    n1 = s1["repo"]["full_name"] if s1.get("repo") else "Repo 1"
    n2 = s2["repo"]["full_name"] if s2.get("repo") else "Repo 2"

    lines = [f"⚖️ Perbandingan Repositori: {n1} vs {n2}\n"]
    if not s1.get("has_data") or not s2.get("has_data"):
        lines.append("Salah satu atau kedua repositori belum memiliki data sentimen.")
        return "\n".join(lines)

    lines.append(f"• Indeks Sentimen (7h): {n1} = {s1['index_7d']} | {n2} = {s2['index_7d']}")
    lines.append(f"• Tren vs 30h Lalu: {n1} = {s1['trend']} | {n2} = {s2['trend']}")
    lines.append(f"• % Negatif (30h): {n1} = {s1['pct_negative']}% | {n2} = {s2['pct_negative']}%")
    lines.append(f"• % Positif (30h): {n1} = {s1['pct_positive']}% | {n2} = {s2['pct_positive']}%")
    lines.append(f"• Komentar 30 hari: {n1} = {s1['comments_30d']} | {n2} = {s2['comments_30d']}")
    if data.get("conclusion"):
        lines.append(f"\n💡 {data['conclusion']}")
    return "\n".join(lines)


def format_sensitivity_info(current: str, updated: bool = False) -> str:
    """Menyusun informasi tingkat sensitivitas alert."""
    prefix = f"✅ Tingkat sensitivitas alert berhasil diubah menjadi: *{current}*.\n\n" if updated else f"⚙️ Sensitivitas alert Anda saat ini: *{current}*.\n\n"
    return (
        f"{prefix}Tingkatan sensitivitas yang tersedia:\n"
        "• *tinggi*: Menerima semua alert (kekuatan lemah, sedang, dan kuat)\n"
        "• *sedang*: Menerima alert tingkat sedang dan kuat (default)\n"
        "• *rendah*: Hanya menerima alert tingkat kuat\n\n"
        "Gunakan `/ambang <rendah|sedang|tinggi>` untuk mengubahnya."
    )
