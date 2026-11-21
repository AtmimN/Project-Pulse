"""Titik masuk eksekusi Bot Telegram ProjectPulse: python -m app.bot."""
from __future__ import annotations

import asyncio
import logging
import sys

from telegram.ext import Application, ApplicationBuilder, CommandHandler

from app import config
from app.bot.handlers import (
    ambang_handler,
    bandingkan_handler,
    berhenti_handler,
    help_handler,
    pantau_handler,
    ringkasan_handler,
    start_handler,
)

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def build_bot_application(token: str) -> Application:
    """Mengonfigurasi dan mendaftarkan seluruh handler perintah Bot Telegram."""
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("bantuan", help_handler))
    app.add_handler(CommandHandler("pantau", pantau_handler))
    app.add_handler(CommandHandler("berhenti", berhenti_handler))
    app.add_handler(CommandHandler("ringkasan", ringkasan_handler))
    app.add_handler(CommandHandler("bandingkan", bandingkan_handler))
    app.add_handler(CommandHandler("ambang", ambang_handler))
    return app


async def _run_polling(token: str) -> None:
    """Coroutine utama: bangun aplikasi dan jalankan polling secara async."""
    app = build_bot_application(token)
    async with app:
        await app.start()
        await app.updater.start_polling()
        await asyncio.Event().wait()  # blokir sampai KeyboardInterrupt


def main() -> None:
    """Menjalankan bot dalam mode polling."""
    token = config.TELEGRAM_BOT_TOKEN.strip()
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN belum diisi di berkas .env.")
        sys.exit(1)

    print("Memulai Bot Telegram ProjectPulse (mode polling)...")
    try:
        asyncio.run(_run_polling(token))
    except (KeyboardInterrupt, SystemExit):
        print("Bot Telegram dihentikan.")


if __name__ == "__main__":
    main()
