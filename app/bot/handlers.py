"""Handler perintah antarmuka Bot Telegram."""
from __future__ import annotations

import logging
from typing import Any

from telegram import Update
from telegram.ext import ContextTypes

from app.bot.formatter import (
    format_comparison,
    format_help_message,
    format_repo_summary,
    format_sensitivity_info,
    format_start_message,
    split_long_message,
)
from app.services import bot_service

logger = logging.getLogger(__name__)


async def _send_reply(update: Update, text: str) -> None:
    """Mengirim balasan pesan yang dipecah rapi jika melebihi batas Telegram."""
    if not update.effective_message:
        return
    for chunk in split_long_message(text):
        try:
            await update.effective_message.reply_text(chunk, parse_mode="Markdown")
        except Exception:
            await update.effective_message.reply_text(chunk)


def _is_private_chat(update: Update) -> bool:
    """Memastikan pesan berasal dari obrolan pribadi (bukan grup atau channel)."""
    return bool(update.effective_chat and update.effective_chat.type == "private")


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /start: mendaftarkan pelanggan dan menampilkan sapaan."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    chat_id = update.effective_user.id
    if not bot_service.check_rate_limit(chat_id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return
    bot_service.register_subscriber(chat_id)
    await _send_reply(update, format_start_message())


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /bantuan: menampilkan daftar panduan perintah."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    if not bot_service.check_rate_limit(update.effective_user.id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return
    await _send_reply(update, format_help_message())


async def pantau_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /pantau <repo>: menambahkan repositori ke watchlist."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    chat_id = update.effective_user.id
    if not bot_service.check_rate_limit(chat_id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return

    if not context.args:
        repos = bot_service.get_available_repos_service()
        if not repos:
            await _send_reply(update, "Belum ada repositori pantau aktif di sistem.")
            return
        repo_list = "\n".join(f"• `{r['full_name']}`" for r in repos)
        await _send_reply(update, f"📋 Repositori yang dapat dipantau:\n\n{repo_list}\n\nGunakan: `/pantau <nama>`")
        return

    res = bot_service.add_watchlist_service(chat_id, context.args[0])
    if res["status"] == "ok":
        name = res["repo"]["full_name"]
        msg = f"✅ Berhasil menambahkan `{name}` ke daftar pantau Anda." if res["added"] else f"ℹ️ `{name}` sudah ada di daftar pantau Anda."
        await _send_reply(update, msg)
    elif res["status"] == "ambiguous":
        matches = "\n".join(f"• `{m}`" for m in res["matches"])
        await _send_reply(update, f"⚠️ Nama repositori ambigu. Silakan pilih spesifik:\n{matches}")
    else:
        avail = "\n".join(f"• `{m}`" for m in res["available"])
        await _send_reply(update, f"❌ Repositori tidak ditemukan. Pilihan yang tersedia:\n{avail}")


async def berhenti_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /berhenti [repo|semua]: menghapus repositori dari watchlist."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    chat_id = update.effective_user.id
    if not bot_service.check_rate_limit(chat_id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return

    if not context.args:
        wl = bot_service.get_watchlist_service(chat_id)
        if not wl:
            await _send_reply(update, "Daftar pantau Anda saat ini kosong.")
            return
        wl_str = "\n".join(f"• `{r['full_name']}`" for r in wl)
        await _send_reply(update, f"📋 Daftar pantau Anda saat ini:\n\n{wl_str}\n\nGunakan: `/berhenti <nama>` atau `/berhenti semua`")
        return

    target = context.args[0].strip().lower()
    if target == "semua":
        deleted = bot_service.clear_watchlist_service(chat_id)
        await _send_reply(update, f"✅ Berhasil mengosongkan watchlist ({deleted} repositori dihapus).")
        return

    res = bot_service.remove_watchlist_service(chat_id, target)
    if res["status"] == "ok":
        await _send_reply(update, f"✅ Berhasil menghapus `{res['repo']['full_name']}` dari daftar pantau Anda.")
    else:
        await _send_reply(update, f"❌ Repositori `{target}` tidak ditemukan di sistem.")


async def ringkasan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /ringkasan [repo]: menampilkan skor sentimen dan metrik."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    chat_id = update.effective_user.id
    if not bot_service.check_rate_limit(chat_id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return

    if context.args:
        from app.db import connection
        with connection.transaction() as conn:
            resolved = bot_service.resolve_monitor_repo(conn, context.args[0])
        if resolved["status"] != "ok":
            await _send_reply(update, f"❌ Repositori `{context.args[0]}` tidak ditemukan atau ambigu.")
            return
        summary = bot_service.get_repo_summary_service(resolved["repo"]["id"])
        await _send_reply(update, format_repo_summary(summary))
        return

    wl = bot_service.get_watchlist_service(chat_id)
    if not wl:
        await _send_reply(update, "Daftar pantau Anda kosong. Tambahkan repositori dengan `/pantau <nama>`.")
        return

    parts = [format_repo_summary(bot_service.get_repo_summary_service(r["id"])) for r in wl]
    sep = "\n\n" + ("=" * 20) + "\n\n"
    await _send_reply(update, sep.join(parts))


async def bandingkan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /bandingkan <repo1> <repo2>: komparasi metrik sentimen."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    chat_id = update.effective_user.id
    if not bot_service.check_rate_limit(chat_id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return

    if not context.args or len(context.args) < 2:
        await _send_reply(update, "Gunakan format: `/bandingkan <repo1> <repo2>`\nContoh: `/bandingkan planka chatwoot`")
        return

    res = bot_service.compare_repos_service(context.args[0], context.args[1])
    if res["status"] != "ok":
        err_repo = res.get("error_repo", "Unknown")
        await _send_reply(update, f"❌ Repositori `{err_repo}` tidak ditemukan atau ambigu.")
        return

    await _send_reply(update, format_comparison(res))


async def ambang_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Menangani perintah /ambang [level]: mengelola preferensi sensitivitas alert."""
    if not _is_private_chat(update) or not update.effective_user:
        return
    chat_id = update.effective_user.id
    if not bot_service.check_rate_limit(chat_id):
        await _send_reply(update, "⚠️ Terlalu banyak permintaan. Silakan tunggu sebentar.")
        return

    arg = context.args[0] if context.args else None
    res = bot_service.get_or_set_sensitivity_service(chat_id, arg)
    if res["status"] == "invalid":
        await _send_reply(update, "❌ Tingkat tidak valid. Pilihan yang tersedia: `rendah`, `sedang`, atau `tinggi`.")
        return

    await _send_reply(update, format_sensitivity_info(res["sensitivity"], updated=res["updated"]))
