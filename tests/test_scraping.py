"""Pengujian scraper komentar dan rilis incremental dengan batas data (DoD M3)."""
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from app import config
from app.db import (
    comments_repo,
    connection,
    daily_stats_repo,
    init_db,
    issues_repo,
    keywords_repo,
    releases_repo,
    repos_repo,
    scrape_state_repo,
)
from app.scraper.github_client import AuthError, GitHubClient, RateLimitError
from app.sentiment.analyzer import VaderSentimentAnalyzer
from app.services.scrape_service import (
    is_bot_user,
    scrape_all_monitor_repos,
    scrape_single_repo,
)


def _setup_test_db(tmp_path: Path) -> Path:
    """Inisialisasi database SQLite sementara untuk pengujian scraping."""
    db_file = tmp_path / "test_scrape.db"
    init_db(db_file)
    with connection.transaction(db_file) as conn:
        repos_repo.add_repo(conn, "owner/repo-one", kind="monitor", active=1)
        repos_repo.add_repo(conn, "owner/repo-two", kind="monitor", active=1)
        keywords_repo.add_keyword(conn, "crash")
        keywords_repo.add_keyword(conn, "error")
    return db_file


def test_bot_detection() -> None:
    """Memastikan akun bertipe Bot, berakhiran [bot], atau di IGNORED_LOGINS tersaring."""
    assert is_bot_user({"type": "Bot", "login": "some-account"}) is True
    assert is_bot_user({"type": "User", "login": "renovate[bot]"}) is True
    assert is_bot_user({"type": "User", "login": "dependabot"}) is True
    assert is_bot_user({"type": "User", "login": "developer-user"}) is False
    assert is_bot_user(None) is False


def test_scrape_incremental_and_deduplication(tmp_path: Path) -> None:
    """Memastikan komentar baru disimpan, dan eksekusi ulang tidak menggandakan data."""
    db_file = _setup_test_db(tmp_path)
    mock_client = MagicMock()
    analyzer = VaderSentimentAnalyzer()

    # Data tiruan issue, komentar, dan rilis
    mock_client.list_issues.return_value = [
        {"number": 10, "state": "open", "created_at": "2024-03-01T00:00:00Z", "updated_at": "2024-03-01T00:00:00Z", "labels": [{"name": "bug"}]}
    ]
    mock_client.list_issue_comments.return_value = [
        {
            "id": 101,
            "issue_url": "https://api.github.com/repos/owner/repo-one/issues/10",
            "body": "Fixed the crash in parser, awesome work!",
            "created_at": "2024-03-01T10:00:00Z",
            "user": {"type": "User", "login": "human_dev"},
        }
    ]
    mock_client.list_review_comments.return_value = []
    mock_client.list_releases.return_value = [
        {"id": 5001, "tag_name": "v1.0.0", "published_at": "2024-03-01T12:00:00Z", "name": "Release 1.0", "draft": False, "prerelease": False}
    ]

    with connection.transaction(db_file) as conn:
        repo = repos_repo.get_by_full_name(conn, "owner/repo-one")
        assert repo is not None

    # Jalankan scraping pertama
    res1 = scrape_single_repo(repo, mock_client, analyzer, db_path=db_file)
    assert res1["status"] == "berhasil"
    assert res1["new_comments"] == 1
    assert res1["new_releases"] == 1

    # Verifikasi data tersimpan
    with connection.transaction(db_file) as conn:
        n_c = comments_repo.count_comments(conn, repo["id"])
        assert n_c == 1
        stats = daily_stats_repo.get_summary_stats(conn, repo["id"], days=30, end_date="2024-03-02")
        assert stats["total_comments"] == 1
        assert stats["total_positive"] == 1
        kw_hits = keywords_repo.get_keyword_daily(conn, repo["id"])
        assert any(k["keyword"] == "crash" and k["n_hits"] == 1 for k in kw_hits)

    # Jalankan scraping kedua dengan data yang sama persis (simulasi komentar yang tidak berubah/hanya diedit)
    res2 = scrape_single_repo(repo, mock_client, analyzer, db_path=db_file)
    assert res2["status"] == "berhasil"
    assert res2["new_comments"] == 0  # Tidak ada duplikasi
    assert res2["new_releases"] == 0

    with connection.transaction(db_file) as conn:
        n_c2 = comments_repo.count_comments(conn, repo["id"])
        assert n_c2 == 1  # Tetap 1, tidak bertambah


def test_data_pruning_and_stats_preservation(tmp_path: Path, monkeypatch) -> None:
    """Memastikan komentar melebihi batas dipangkas, dan daily_stats / keyword_daily tidak berkurang."""
    db_file = _setup_test_db(tmp_path)
    monkeypatch.setattr(config, "MAX_COMMENTS_PER_REPO", 3)  # Pasang batas kecil 3 komentar

    mock_client = MagicMock()
    analyzer = VaderSentimentAnalyzer()
    mock_client.list_issues.return_value = []
    mock_client.list_releases.return_value = []
    mock_client.list_review_comments.return_value = []

    # Buat 5 komentar berurutan
    comments_payload = []
    for i in range(1, 6):
        comments_payload.append({
            "id": 200 + i,
            "issue_url": "https://api.github.com/repos/owner/repo-one/issues/1",
            "body": f"Comment number {i} regarding error",
            "created_at": f"2024-03-0{i}T10:00:00Z",
            "user": {"type": "User", "login": f"user_{i}"},
        })
    mock_client.list_issue_comments.return_value = comments_payload

    with connection.transaction(db_file) as conn:
        repo = repos_repo.get_by_full_name(conn, "owner/repo-one")
        assert repo is not None

    res = scrape_single_repo(repo, mock_client, analyzer, db_path=db_file)
    assert res["status"] == "berhasil"
    assert res["new_comments"] == 5

    with connection.transaction(db_file) as conn:
        # 1. Tabel comments tepat sama dengan batas (3 komentar)
        c_count = comments_repo.count_comments(conn, repo["id"])
        assert c_count == 3

        # Komentar terlama (id 201 dan 202) telah dihapus
        remaining = comments_repo.list_comments_page(conn, repo["id"], limit=10)
        remaining_ids = [r["comment_id"] for r in remaining]
        assert 201 not in remaining_ids
        assert 202 not in remaining_ids
        assert 205 in remaining_ids

        # 2. daily_stats TIDAK berkurang (total tetap 5)
        stats = daily_stats_repo.get_summary_stats(conn, repo["id"], days=30, end_date="2024-03-10")
        assert stats["total_comments"] == 5

        # 3. keyword_daily TIDAK berkurang
        kw_hits = keywords_repo.get_keyword_daily(conn, repo["id"])
        total_error_hits = sum(k["n_hits"] for k in kw_hits if k["keyword"] == "error")
        assert total_error_hits == 5

        # 4. floor_created_at diperbarui ke komentar terbaru yang dipangkas (2024-03-02T10:00:00Z)
        st = scrape_state_repo.get_scrape_state(conn, repo["id"], "issue_comments")
        assert st is not None
        assert st["floor_created_at"] == "2024-03-02T10:00:00Z"


def test_rate_limit_and_error_handling(tmp_path: Path) -> None:
    """Menguji penanganan RateLimitError yang melewati repositori berikutnya dan isolasi kegagalan."""
    db_file = _setup_test_db(tmp_path)
    mock_client = MagicMock()

    # Repositori pertama memicu RateLimitError
    def fake_list_issues(full_name: str, since: str | None = None):
        if "repo-one" in full_name:
            raise RateLimitError("Rate limit reached for test", reset_at=1700000000)
        return []

    mock_client.list_issues.side_effect = fake_list_issues
    mock_client.list_issue_comments.return_value = []
    mock_client.list_review_comments.return_value = []
    mock_client.list_releases.return_value = []

    res_all = scrape_all_monitor_repos(github_client=mock_client, db_path=db_file)
    results = res_all["results"]
    assert len(results) >= 2
    assert results[0]["status"] == "dilewati"
    assert all(r["status"] == "dilewati" for r in results)  # Semua repositori berikutnya dilewati saat rate limit


def test_releases_draft_and_prerelease(tmp_path: Path) -> None:
    """Memastikan rilis draft diabaikan dan penanda prerelease tersimpan dengan benar."""
    db_file = _setup_test_db(tmp_path)
    mock_client = MagicMock()
    analyzer = VaderSentimentAnalyzer()

    mock_client.list_issues.return_value = []
    mock_client.list_issue_comments.return_value = []
    mock_client.list_review_comments.return_value = []
    mock_client.list_releases.return_value = [
        {"id": 1, "tag_name": "v1.0.0-draft", "published_at": "2024-01-01T00:00:00Z", "draft": True, "prerelease": False},
        {"id": 2, "tag_name": "v1.0.0-rc1", "published_at": "2024-01-02T00:00:00Z", "draft": False, "prerelease": True},
        {"id": 3, "tag_name": "v1.0.0", "published_at": "2024-01-03T00:00:00Z", "draft": False, "prerelease": False},
    ]

    with connection.transaction(db_file) as conn:
        repo = repos_repo.get_by_full_name(conn, "owner/repo-one")
        assert repo is not None

    res = scrape_single_repo(repo, mock_client, analyzer, db_path=db_file)
    assert res["new_releases"] == 2  # Hanya id 2 dan id 3 (draft diabaikan)

    with connection.transaction(db_file) as conn:
        latest = releases_repo.get_latest_release(conn, repo["id"])
        assert latest is not None
        assert latest["tag"] == "v1.0.0"
        assert latest["prerelease"] == 0
