"""Modul pengiriman notifikasi Telegram untuk alert dan digest harian."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from app import config
from app.db import connection, subscribers_repo

logger = logging.getLogger(__name__)


async def _dispatch_send(bot: Any, chat_id: int | str, text: str) -> bool:
    """Mengirim pesan via coroutine bot atau pemanggilan langsung objek tiruan."""
    res = bot.send_message(chat_id=int(chat_id), text=text)
    if asyncio.iscoroutine(res):
        await res
    return True


def _run_send(bot: Any, chat_id: int | str, text: str) -> bool:
    """Mengeksekusi coroutine pengiriman dengan menangani event loop yang sedang berjalan."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return bool(pool.submit(asyncio.run, _dispatch_send(bot, chat_id, text)).result())
        return asyncio.run(_dispatch_send(bot, chat_id, text))
    except RuntimeError:
        return asyncio.run(_dispatch_send(bot, chat_id, text))


def _handle_send_error(err: Exception, chat_id: int | str, db_path: str | Path | None) -> None:
    """Menangani error pengiriman pesan Telegram termasuk pemblokiran bot."""
    err_msg = str(err).lower()
    if "forbidden" in err_msg or "blocked" in err_msg:
        logger.warning("Pelanggan %s memblokir bot, menandai nonaktif.", chat_id)
        with connection.transaction(db_path) as conn:
            subscribers_repo.set_active(conn, int(chat_id), 0)
    else:
        logger.error("Gagal mengirim pesan Telegram (%s).", type(err).__name__)


def send_text(
    chat_id: int | str,
    text: str,
    token: str | None = None,
    db_path: str | Path | None = None,
    bot_client: Any = None,
) -> bool:
    """Mengirim teks ke chat_id dan menangani pemblokiran serta kesalahan jaringan."""
    bot_token = token or config.TELEGRAM_BOT_TOKEN
    if not bot_token and not bot_client:
        logger.warning("TELEGRAM_BOT_TOKEN kosong, pesan tidak dapat dikirim.")
        return False

    try:
        bot = bot_client
        if not bot:
            from telegram import Bot
            bot = Bot(token=bot_token)
        return _run_send(bot, chat_id, text)
    except Exception as err:
        _handle_send_error(err, chat_id, db_path)
        return False


class TelegramNotifier:
    """Adapter pengirim notifikasi yang kompatibel dengan alert_service."""

    def __init__(self, token: str | None = None, db_path: str | Path | None = None, bot_client: Any = None):
        self.token = token or config.TELEGRAM_BOT_TOKEN
        self.db_path = db_path
        self.bot_client = bot_client

    def send_message(self, chat_id: int | str, text: str) -> bool:
        """Mengirim pesan ke pelanggan."""
        return send_text(chat_id, text, token=self.token, db_path=self.db_path, bot_client=self.bot_client)
