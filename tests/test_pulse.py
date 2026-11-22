"""Pengujian halaman Pulse Repositori (Milestone M6)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from flask.testing import FlaskClient

from app.db import connection, repos_repo
from app.services import pulse_service


def test_pulse_page_empty_repos(client: FlaskClient) -> None:
    """Menguji tampilan halaman Pulse Repositori ketika belum ada repositori pantau."""
    response = client.get("/repositori")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Belum Ada Repositori Pantau" in html
    assert "Target: Milestone M3" not in html


def test_pulse_page_empty_comments(client: FlaskClient, temp_db_path: Path) -> None:
    """Menguji tampilan repositori pantau yang belum memiliki data komentar."""
    with connection.transaction(temp_db_path) as conn:
        repos_repo.add_repo(conn, "test-org/empty-repo", kind="monitor")

    response = client.get("/repositori")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Belum Ada Data Komentar untuk test-org/empty-repo" in html
    assert "Target: Milestone M3" not in html


def test_pulse_page_with_data_and_filters(client: FlaskClient, temp_db_path: Path) -> None:
    """Menguji tampilan lengkap Pulse Repositori: metrik 30 hari, rilis, kata teratas, dan filter."""
    today_str = datetime.now().date().strftime("%Y-%m-%d")
    with connection.transaction(temp_db_path) as conn:
        r1 = repos_repo.add_repo(conn, "org/full-repo", kind="monitor")
        conn.execute(
            "INSERT INTO releases (repo_id, release_id, tag, published_at) VALUES (?, 1001, 'v1.5.0', '2026-05-01T10:00:00Z')",
            (r1,),
        )
        conn.execute(
            "INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) "
            "VALUES (?, ?, 15, 10, 3, 2)",
            (r1, today_str),
        )
        # Tambah beberapa komentar
        conn.execute(
            "INSERT INTO comments (repo_id, kind, comment_id, issue_number, is_pr, labels, body, created_at, sentiment_label) "
            "VALUES (?, 'issue_comment', 101, 1, 0, '[\"bug\"]', 'Great feature excellent job', ?, 'positif')",
            (r1, today_str),
        )
        conn.execute(
            "INSERT INTO comments (repo_id, kind, comment_id, issue_number, is_pr, labels, body, created_at, sentiment_label) "
            "VALUES (?, 'issue_comment', 102, 2, 1, '[]', 'Terrible crash bad performance', ?, 'negatif')",
            (r1, today_str),
        )

    # Akses tanpa filter
    res = client.get(f"/repositori?repo={r1}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "org/full-repo" in html
    assert "v1.5.0" in html
    assert "Indeks Sentimen (30 Hari)" in html
    assert "Great feature excellent job" in html
    assert "Terrible crash bad performance" in html
    assert "Target: Milestone M3" not in html

    # Filter positif
    res_pos = client.get(f"/repositori?repo={r1}&filter=positif")
    assert res_pos.status_code == 200
    html_pos = res_pos.get_data(as_text=True)
    assert "Great feature excellent job" in html_pos
    assert "Terrible crash bad performance" not in html_pos

    # Filter negatif
    res_neg = client.get(f"/repositori?repo={r1}&filter=negatif")
    assert res_neg.status_code == 200
    html_neg = res_neg.get_data(as_text=True)
    assert "Terrible crash bad performance" in html_neg
    assert "Great feature excellent job" not in html_neg


def test_pulse_top_words_and_validation(temp_db_path: Path) -> None:
    """Menguji ekstraksi kata teratas dan pembacaan informasi validasi sentimen."""
    today_str = datetime.now().date().strftime("%Y-%m-%d")
    with connection.transaction(temp_db_path) as conn:
        r = repos_repo.add_repo(conn, "org/words-repo", kind="monitor")
        conn.execute(
            "INSERT INTO comments (repo_id, kind, comment_id, issue_number, is_pr, labels, body, created_at, sentiment_label) "
            "VALUES (?, 'issue_comment', 201, 10, 0, '[]', 'awesome optimization awesome awesome', ?, 'positif')",
            (r, today_str),
        )

    data = pulse_service.get_pulse_data(r, db_path=temp_db_path)
    assert data["has_data"] is True
    top_pos = dict(data["top_words_positive"])
    assert "awesome" in top_pos
    assert top_pos["awesome"] == 3
    assert "the" not in top_pos  # Stopword tersaring
