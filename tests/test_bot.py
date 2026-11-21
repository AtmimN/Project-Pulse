"""Pengujian fungsionalitas Bot Telegram, handler perintah, formatter, dan notifier."""
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app.bot.formatter import escape_text, split_long_message
from app.bot.handlers import (
    ambang_handler, bandingkan_handler, berhenti_handler,
    pantau_handler, ringkasan_handler, start_handler,
)
from app.bot.notifier import send_text
from app.db import connection, repos_repo, subscribers_repo
from app.services import bot_service


class MockMessage:
    def __init__(self):
        self.replies: list[str] = []

    async def reply_text(self, text: str, **kwargs):
        self.replies.append(text)


class MockUpdate:
    def __init__(self, chat_type: str = "private", user_id: int = 12345):
        self.effective_chat = type("Chat", (), {"type": chat_type, "id": user_id})()
        self.effective_user = type("User", (), {"id": user_id})()
        self.effective_message = MockMessage()


class MockContext:
    def __init__(self, args: list[str] | None = None):
        self.args = args or []


@pytest.fixture
def test_db(tmp_path: Path) -> Path:
    """Membuat basis data sementara dengan skema lengkap."""
    db_file = tmp_path / "test_bot.db"
    conn = sqlite3.connect(db_file)
    schema_sql = (Path(__file__).resolve().parent.parent / "app" / "db" / "schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.close()
    return db_file


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Mereset pembatasan laju antar tes."""
    bot_service.reset_rate_limits()


def test_formatter_escape_and_split():
    """Menguji pembersihan teks komentar tak tepercaya dan pemecahan pesan panjang."""
    raw = "<script>alert('hack')</script>"
    assert escape_text(raw) == "&lt;script&gt;alert(&#x27;hack&#x27;)&lt;/script&gt;"

    long_text = "Baris data\n" * 500
    chunks = split_long_message(long_text, max_length=1000)
    assert len(chunks) > 1 and all(len(c) <= 1000 for c in chunks)


def test_bot_start_registration_idempotent(test_db: Path, monkeypatch):
    """Menguji pendaftaran pelanggan baru dan idempoten bila dipanggil dua kali."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(test_db))
    update, context = MockUpdate(chat_type="private", user_id=999), MockContext()

    asyncio.run(start_handler(update, context))
    assert "Selamat datang" in update.effective_message.replies[0]
    with connection.transaction(test_db) as conn:
        assert len(subscribers_repo.list_subscribers(conn)) == 1

    asyncio.run(start_handler(update, context))
    with connection.transaction(test_db) as conn:
        assert len(subscribers_repo.list_subscribers(conn)) == 1


def test_bot_pantau_and_berhenti_resolution(test_db: Path, monkeypatch):
    """Menguji /pantau dan /berhenti dengan nama lengkap, nama pendek, dan penolakan nama asing."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(test_db))
    with connection.transaction(test_db) as conn:
        repos_repo.add_repo(conn, "planka-org/planka", kind="monitor")
        repos_repo.add_repo(conn, "chatwoot/chatwoot", kind="monitor")

    uid = 888
    up_list = MockUpdate(user_id=uid)
    asyncio.run(pantau_handler(up_list, MockContext()))
    assert "planka-org/planka" in up_list.effective_message.replies[0]

    up_add = MockUpdate(user_id=uid)
    asyncio.run(pantau_handler(up_add, MockContext(["planka"])))
    assert "Berhasil menambahkan" in up_add.effective_message.replies[0]

    up_unk = MockUpdate(user_id=uid)
    asyncio.run(pantau_handler(up_unk, MockContext(["unknown-repo"])))
    assert "tidak ditemukan" in up_unk.effective_message.replies[0]

    up_del = MockUpdate(user_id=uid)
    asyncio.run(berhenti_handler(up_del, MockContext(["planka"])))
    assert "Berhasil menghapus" in up_del.effective_message.replies[0]

    up_clr = MockUpdate(user_id=uid)
    asyncio.run(berhenti_handler(up_clr, MockContext(["semua"])))
    assert "mengosongkan watchlist" in up_clr.effective_message.replies[0]


def test_bot_ringkasan_and_bandingkan(test_db: Path, monkeypatch):
    """Menguji /ringkasan dan /bandingkan dengan data kosong maupun data riil."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(test_db))
    with connection.transaction(test_db) as conn:
        r1 = repos_repo.add_repo(conn, "org/repo-a", kind="monitor")
        repos_repo.add_repo(conn, "org/repo-b", kind="monitor")
        conn.execute("INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) VALUES (?, 'issue_comment', 1, 101, 'good', '2026-05-10')", (r1,))
        conn.execute("INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) VALUES (?, '2026-05-10', 10, 8, 1, 1)", (r1,))

    up_empty = MockUpdate(user_id=777)
    asyncio.run(ringkasan_handler(up_empty, MockContext(["repo-b"])))
    assert "Belum ada data" in up_empty.effective_message.replies[0]

    up_sum = MockUpdate(user_id=777)
    asyncio.run(ringkasan_handler(up_sum, MockContext(["repo-a"])))
    assert "Ringkasan Repositori: org/repo-a" in up_sum.effective_message.replies[0]

    up_cmp = MockUpdate(user_id=777)
    asyncio.run(bandingkan_handler(up_cmp, MockContext(["repo-a", "repo-b"])))
    assert "Perbandingan Repositori" in up_cmp.effective_message.replies[0]


def test_bot_ambang_sensitivity_config(test_db: Path, monkeypatch):
    """Menguji /ambang untuk melihat dan memperbarui tingkat sensitivitas."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(test_db))
    uid = 666
    up_get = MockUpdate(user_id=uid)
    asyncio.run(ambang_handler(up_get, MockContext()))
    assert "sedang" in up_get.effective_message.replies[0]

    up_set = MockUpdate(user_id=uid)
    asyncio.run(ambang_handler(up_set, MockContext(["tinggi"])))
    assert "berhasil diubah menjadi: *tinggi*" in up_set.effective_message.replies[0]

    up_inv = MockUpdate(user_id=uid)
    asyncio.run(ambang_handler(up_inv, MockContext(["ekstrem"])))
    assert "Tingkat tidak valid" in up_inv.effective_message.replies[0]


def test_bot_notifier_blocked_user_inactive(test_db: Path):
    """Menguji bahwa saat bot diblokir pengguna (Forbidden), notifier menandainya nonaktif."""
    with connection.transaction(test_db) as conn:
        subscribers_repo.add_or_update_subscriber(conn, 555)

    try:
        from telegram.error import Forbidden
        mock_err = Forbidden("Forbidden: bot was blocked by the user")
    except ImportError:
        mock_err = Exception("Forbidden: bot was blocked by the user")

    mock_bot = MagicMock()
    mock_bot.send_message.side_effect = mock_err
    assert send_text(555, "Halo", token="test_token", db_path=test_db, bot_client=mock_bot) is False

    with connection.transaction(test_db) as conn:
        assert subscribers_repo.get_subscriber(conn, 555)["active"] == 0


def test_bot_group_chat_and_rate_limit():
    """Memastikan pesan non-privat diabaikan dan pembatasan laju 10/menit berfungsi."""
    up_grp = MockUpdate(chat_type="group", user_id=444)
    asyncio.run(start_handler(up_grp, MockContext()))
    assert len(up_grp.effective_message.replies) == 0

    uid = 333
    for _ in range(10):
        assert bot_service.check_rate_limit(uid, max_per_minute=10) is True
    assert bot_service.check_rate_limit(uid, max_per_minute=10) is False
