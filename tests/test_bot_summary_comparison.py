"""Pengujian perbaikan /ringkasan dan /bandingkan pada Bot Telegram."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import pytest

from app import config
from app.bot.formatter import format_comparison, format_repo_summary
from app.bot.handlers import bandingkan_handler, ringkasan_handler
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


@pytest.fixture(autouse=True)
def clean_rate_limits():
    """Mereset catatan pembatasan laju antar pengujian."""
    bot_service.reset_rate_limits()


def test_ringkasan_insufficient_comments_30d(temp_db_path: Path, monkeypatch):
    """(1) Menguji repositori dengan komentar 30 hari < MIN_COMMENTS_FOR_SUMMARY."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(temp_db_path))
    today_str = datetime.now().date().strftime("%Y-%m-%d")

    with connection.transaction(temp_db_path) as conn:
        r1 = repos_repo.add_repo(conn, "test-org/repo-few", kind="monitor")
        conn.execute(
            "INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) "
            "VALUES (?, 'issue_comment', 1, 101, 'few', ?)",
            (r1, today_str),
        )
        # Hanya 5 komentar dalam 30 hari (kurang dari batas 10)
        conn.execute(
            "INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) "
            "VALUES (?, ?, 5, 4, 1, 0)",
            (r1, today_str),
        )

    summary = bot_service.get_repo_summary_service(r1, temp_db_path)
    text = format_repo_summary(summary)

    # Harus menampilkan kalimat data belum cukup dengan n = 5
    assert "Data belum cukup (n = 5 komentar dalam 30 hari)" in text
    # Tidak boleh mencetak 0 / persentase / tren sentimen
    assert "0.0%" not in text
    assert "Positif" not in text
    assert "Indeks Sentimen 7 Hari:" not in text


def test_ringkasan_sufficient_30d_but_few_7d(temp_db_path: Path, monkeypatch):
    """(1) Menguji 30 hari cukup data namun 7 hari < MIN_COMMENTS_FOR_SUMMARY."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(temp_db_path))
    d_today = datetime.now().date()
    today_str = d_today.strftime("%Y-%m-%d")
    d15_str = (d_today - timedelta(days=15)).strftime("%Y-%m-%d")

    with connection.transaction(temp_db_path) as conn:
        r2 = repos_repo.add_repo(conn, "test-org/repo-mid", kind="monitor")
        conn.execute(
            "INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) "
            "VALUES (?, 'issue_comment', 2, 102, 'cmt', ?)",
            (r2, today_str),
        )
        # 4 komentar di 7 hari (sedikit data)
        conn.execute(
            "INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) "
            "VALUES (?, ?, 4, 3, 1, 0)",
            (r2, today_str),
        )
        # 12 komentar di 15 hari lalu (total 30 hari = 16 >= 10)
        conn.execute(
            "INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) "
            "VALUES (?, ?, 12, 8, 2, 2)",
            (r2, d15_str),
        )

    summary = bot_service.get_repo_summary_service(r2, temp_db_path)
    text = format_repo_summary(summary)

    # Indeks 7 hari menampilkan jumlah komentar dan (sedikit data)
    assert "4 komentar" in text
    assert "(sedikit data)" in text
    # Sebaran 30 hari ditampilkan karena total 30 hari >= 10
    assert "Sebaran Sentimen 30 Hari: Positif" in text


def test_bandingkan_komentar_30_hari_and_no_conclusion_on_insufficient(temp_db_path: Path, monkeypatch):
    """(2) Menguji /bandingkan menampilkan Komentar 30 hari dan tidak ada kesimpulan bila data kurang."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(temp_db_path))
    today_str = datetime.now().date().strftime("%Y-%m-%d")

    with connection.transaction(temp_db_path) as conn:
        r1 = repos_repo.add_repo(conn, "org/repo-c1", kind="monitor")
        r2 = repos_repo.add_repo(conn, "org/repo-c2", kind="monitor")
        conn.execute("INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) VALUES (?, 'issue_comment', 10, 10, 'x', ?)", (r1, today_str))
        conn.execute("INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) VALUES (?, 'issue_comment', 11, 11, 'y', ?)", (r2, today_str))
        # r1 punya 20 komentar (cukup), r2 hanya 3 komentar (belum cukup)
        conn.execute("INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) VALUES (?, ?, 20, 15, 3, 2)", (r1, today_str))
        conn.execute("INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) VALUES (?, ?, 3, 2, 1, 0)", (r2, today_str))

    up_cmp = MockUpdate(user_id=777)
    asyncio.run(bandingkan_handler(up_cmp, MockContext(["repo-c1", "repo-c2"])))
    reply = up_cmp.effective_message.replies[0]

    # Menampilkan 'Komentar 30 hari', bukan total tersimpan
    assert "• Komentar 30 hari:" in reply
    assert "Total tersimpan" not in reply
    assert "Total Komentar" not in reply
    # Tidak menulis kesimpulan karena salah satu repositori (r2) datanya belum cukup
    assert "💡" not in reply


def test_bandingkan_writes_conclusion_when_both_sufficient(temp_db_path: Path, monkeypatch):
    """(2) Menguji /bandingkan menulis kalimat kesimpulan bila kedua repositori cukup data."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(temp_db_path))
    today_str = datetime.now().date().strftime("%Y-%m-%d")

    with connection.transaction(temp_db_path) as conn:
        r1 = repos_repo.add_repo(conn, "org/repo-ok1", kind="monitor")
        r2 = repos_repo.add_repo(conn, "org/repo-ok2", kind="monitor")
        conn.execute("INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) VALUES (?, 'issue_comment', 20, 20, 'a', ?)", (r1, today_str))
        conn.execute("INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) VALUES (?, 'issue_comment', 21, 21, 'b', ?)", (r2, today_str))
        conn.execute("INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) VALUES (?, ?, 15, 12, 2, 1)", (r1, today_str))
        conn.execute("INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) VALUES (?, ?, 15, 5, 5, 5)", (r2, today_str))

    up_cmp = MockUpdate(user_id=777)
    asyncio.run(bandingkan_handler(up_cmp, MockContext(["repo-ok1", "repo-ok2"])))
    reply = up_cmp.effective_message.replies[0]

    assert "• Komentar 30 hari:" in reply
    assert "💡" in reply
    assert "lebih tinggi dibanding" in reply


def test_ringkasan_separator_does_not_stick_to_title(temp_db_path: Path, monkeypatch):
    """(3) Menguji baris pemisah antar repositori di /ringkasan tidak menempel pada judul."""
    monkeypatch.setattr("app.config.DATABASE_PATH", str(temp_db_path))
    uid = 999
    with connection.transaction(temp_db_path) as conn:
        r1 = repos_repo.add_repo(conn, "org/repo-sep1", kind="monitor")
        r2 = repos_repo.add_repo(conn, "org/repo-sep2", kind="monitor")
        subscribers_repo.add_or_update_subscriber(conn, uid)
        subscribers_repo.add_to_watchlist(conn, uid, r1)
        subscribers_repo.add_to_watchlist(conn, uid, r2)

    up = MockUpdate(user_id=uid)
    asyncio.run(ringkasan_handler(up, MockContext()))
    reply = up.effective_message.replies[0]

    # Baris pemisah tidak menempel pada judul repositori pertama
    assert not reply.startswith("=")
    assert reply.startswith("📊 Ringkasan Repositori:") or reply.startswith("📊 org/repo-sep1")
    # Pemisah berada di antara kedua ringkasan repositori dengan jarak baris
    assert "\n\n====================\n\n" in reply
