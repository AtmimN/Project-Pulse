"""Modul registri handler untuk intent dinamis chatbot ProjectPulse."""
from __future__ import annotations

from typing import Any, Callable


def format_date_id(date_str: str | None) -> str:
    """Memformat string tanggal ISO menjadi format tanggal ringkas Indonesia."""
    if not date_str:
        return "-"
    parts = date_str.split("T")[0].split("-")
    if len(parts) == 3:
        months = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Ags", "Sep", "Okt", "Nov", "Des"]
        try:
            m_idx = int(parts[1])
            m_name = months[m_idx] if 1 <= m_idx <= 12 else parts[1]
            return f"{int(parts[2])} {m_name} {parts[0]}"
        except ValueError:
            return date_str
    return date_str


def _find_repo_match(pesan_lower: str, repos_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Mencari repositori yang cocok berdasarkan full_name atau short name."""
    for r in repos_list:
        full_name = r["full_name"]
        short_name = full_name.split("/")[-1]
        if full_name.lower() in pesan_lower or short_name.lower() in pesan_lower:
            return r
    return None


def _format_sentiment_summary(repo: dict[str, Any]) -> str:
    """Menyusun teks balasan ringkasan sentimen untuk repositori yang ditemukan."""
    full_name = repo["full_name"]
    stats = repo.get("stats", {})
    total = stats.get("total_comments", 0)

    if total == 0:
        return f"Belum ada data komentar untuk {full_name}. Data diperbarui otomatis oleh penjadwal harian."

    pos = stats.get("total_positive", 0)
    neu = stats.get("total_neutral", 0)
    neg = stats.get("total_negative", 0)

    pos_pct = round((pos / total) * 100)
    neu_pct = round((neu / total) * 100)
    neg_pct = round((neg / total) * 100)

    release_info = repo.get("latest_release")
    if release_info and release_info.get("tag"):
        rel_str = f"Rilis terbaru: {release_info['tag']} ({format_date_id(release_info.get('published_at'))})."
    else:
        rel_str = "Belum ada rilis stabil."

    last_updated = format_date_id(stats.get("latest_stat_date") or repo.get("last_updated"))

    return (
        f"{full_name} (30 hari terakhir): {pos_pct}% komentar positif, {neu_pct}% netral, "
        f"{neg_pct}% negatif dari {total} komentar. {rel_str} Data terakhir diperbarui {last_updated}."
    )


def repo_sentiment_handler(pesan: str, provider: Any) -> str:
    """Handler intent dinamis repo_sentiment yang membaca sentimen repositori pantau."""
    if not provider or not hasattr(provider, "get_repo_sentiment_info"):
        return "Layanan sentimen repositori tidak tersedia saat ini."

    info = provider.get_repo_sentiment_info()
    repos_list = info.get("active_repos", [])
    if not repos_list:
        return "Belum ada repositori pantau yang terdaftar di sistem."

    matched_repo = _find_repo_match(pesan.lower(), repos_list)
    if not matched_repo:
        repo_names = ", ".join(r["full_name"] for r in repos_list)
        return (
            f"Repositori tidak ditemukan dalam pesanmu. "
            f"Repositori pantau yang tersedia: {repo_names}."
        )

    return _format_sentiment_summary(matched_repo)


# Registri pemetaan nama handler string ke fungsi
HANDLERS: dict[str, Callable[[str, Any], str]] = {
    "repo_sentiment": repo_sentiment_handler,
}
