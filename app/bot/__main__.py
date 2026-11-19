"""Titik masuk eksekusi Bot Telegram: python -m app.bot."""
import sys
from app import config

if __name__ == "__main__":
    if not config.TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN belum diisi di berkas .env.")
        sys.exit(1)
    print("Bot Telegram ProjectPulse (tersedia pada Milestone M5).")
