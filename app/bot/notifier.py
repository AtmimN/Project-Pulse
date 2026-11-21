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
        from telegram.error import Forbidden, RetryAfter, TelegramError
    except ImportError:
        Forbidden = Exception
        RetryAfter = Exception
        TelegramError = Exception

    try:
        if bot_client:
            bot = bot_client
        else:
            from telegram import Bot
            bot = Bot(token=bot_token)

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Jika event loop sudah aktif di thread ini (misal dalam context asyncio)
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    success = pool.submit(asyncio.run, _dispatch_send(bot, chat_id, text)).result()
                    return bool(success)
            else:
                return asyncio.run(_dispatch_send(bot, chat_id, text))
        except RuntimeError:
            return asyncio.run(_dispatch_send(bot, chat_id, text))

    except Forbidden:
        logger.warning("Pelanggan %s memblokir bot, menandai sebagai nonaktif.", chat_id)
        with connection.transaction(db_path) as conn:
            subscribers_repo.set_active(conn, int(chat_id), 0)
        return False
    except RetryAfter as err:
        logger.warning("Batas laju Telegram (RetryAfter %s detik).", getattr(err, "retry_after", 0))
        return False
    except (TelegramError, Exception) as err:
        err_msg = str(err).lower()
        if "forbidden" in err_msg or "blocked" in err_msg:
            with connection.transaction(db_path) as conn:
                subscribers_repo.set_active(conn, int(chat_id), 0)
        logger.error("Gagal mengirim pesan Telegram (%s).", type(err).__name__)
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
