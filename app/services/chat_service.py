"""Layanan logika bisnis percakapan chatbot ProjectPulse."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app import config
from app.chatbot.engine import ChatbotEngine, load_intents
from app.chatbot.handlers import HANDLERS
from app.db import connection, conversations_repo, daily_stats_repo, releases_repo, repos_repo


class RepoSentimentProvider:
    """Penyedia data sentimen dan rilis dari database untuk intent dinamis chatbot."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = db_path

    def get_repo_sentiment_info(self) -> dict[str, Any]:
        """Mengambil data agregasi sentimen 30 hari dan rilis untuk repositori pantau aktif."""
        with connection.transaction(self.db_path) as conn:
            active_repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
            results = []
            for r in active_repos:
                stats = daily_stats_repo.get_summary_stats(conn, r["id"], days=30)
                latest_rel = releases_repo.get_latest_release(conn, r["id"])
                results.append(
                    {
                        "id": r["id"],
                        "full_name": r["full_name"],
                        "stats": stats,
                        "latest_release": latest_rel,
                        "last_updated": stats.get("latest_stat_date"),
                    }
                )
        return {"active_repos": results}


def get_chatbot_engine(db_path: str | Path | None = None) -> ChatbotEngine:
    """Membangun instance ChatbotEngine dengan dependensi data yang disuntikkan."""
    intents_data = load_intents()
    provider = RepoSentimentProvider(db_path)
    return ChatbotEngine(
        intents_data=intents_data,
        threshold=0.45,
        handlers=HANDLERS,
        provider=provider,
    )


def process_chat(
    message: str,
    session_id: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Memproses pesan masuk dari pengguna, mendapatkan balasan, dan mencatat log."""
    cleaned = message.strip()
    if not cleaned:
        raise ValueError("Pesan tidak boleh kosong.")

    if len(message) > config.MAX_MESSAGE_LEN:
        raise ValueError(
            f"Panjang pesan melebihi batas maksimal {config.MAX_MESSAGE_LEN} karakter."
        )

    engine = get_chatbot_engine(db_path)
    result = engine.reply(cleaned)

    # Catat ke conversation_logs dalam transaksi terpisah
    with connection.transaction(db_path) as conn:
        conversations_repo.log_conversation(
            conn=conn,
            session_id=session_id,
            message=cleaned,
            reply=result["reply"],
            intent=result["intent"],
        )

    return {
        "reply": result["reply"],
        "intent": result["intent"],
        "score": result["score"],
    }
