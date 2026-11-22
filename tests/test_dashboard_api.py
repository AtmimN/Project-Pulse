"""Pengujian endpoint REST API dan data dashboard (Milestone M6)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from flask.testing import FlaskClient

from app.db import connection, repos_repo


def test_api_dashboard_endpoints(client: FlaskClient, temp_db_path: Path) -> None:
    """Menguji ketersediaan dan struktur respons seluruh endpoint REST API dashboard."""
    today_str = datetime.now().date().strftime("%Y-%m-%d")
    with connection.transaction(temp_db_path) as conn:
        r = repos_repo.add_repo(conn, "test/dashboard-repo", kind="monitor")
        conn.execute(
            "INSERT INTO daily_stats (repo_id, stat_date, n_comments, n_positive, n_neutral, n_negative) "
            "VALUES (?, ?, 10, 7, 2, 1)",
            (r, today_str),
        )
        conn.execute("INSERT INTO comments (repo_id, kind, comment_id, issue_number, body, created_at) VALUES (?, 'issue_comment', 1, 1, 'c', ?)", (r, today_str))
        conn.execute(
            "INSERT INTO alerts (repo_id, alert_type, strength, detail, alert_date, dedupe_key) "
            "VALUES (?, 'spike', 'sedang', '{\"ratio\": 2.5}', ?, 'test_key_1')",
            (r, today_str),
        )

    # 1. Summary
    res = client.get("/api/dashboard/summary")
    assert res.status_code == 200
    d = res.get_json()
    assert d["comments_30d"] == 10
    assert d["monitor_repos_count"] >= 1
    assert d["top_sentiment_repo"] is not None
    assert d["top_sentiment_repo"]["name"] == "test/dashboard-repo"

    # 2. Sentiment by repo
    res = client.get("/api/dashboard/sentiment-by-repo")
    assert res.status_code == 200
    d = res.get_json()
    assert len(d) >= 1
    assert any(x["repo"] == "test/dashboard-repo" for x in d)

    # 3. Sentiment trend
    res = client.get("/api/dashboard/sentiment-trend")
    assert res.status_code == 200
    d = res.get_json()
    assert isinstance(d, list)

    # 4. Regression A
    res = client.get("/api/dashboard/regression-a")
    assert res.status_code == 200
    d = res.get_json()
    assert "status" in d or "cv_mae" in d

    # 5. Regression B
    res = client.get("/api/dashboard/regression-b")
    assert res.status_code == 200
    d = res.get_json()
    assert "status" in d or "test_mae_person_months" in d

    # 6. Training data
    res = client.get("/api/dashboard/training-data")
    assert res.status_code == 200
    d = res.get_json()
    assert "included_count" in d
    assert "exclusion_reasons" in d

    # 7. Recent estimations
    res = client.get("/api/dashboard/recent-estimations")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)

    # 8. Recent alerts
    res = client.get("/api/dashboard/recent-alerts")
    assert res.status_code == 200
    d = res.get_json()
    assert len(d) >= 1
    assert d[0]["alert_type"] == "spike"

    # 9. Scheduler status
    res = client.get("/api/dashboard/scheduler-status")
    assert res.status_code == 200
    d = res.get_json()
    assert "schedule" in d


def test_dashboard_model_a_and_b_pairs_api(client: FlaskClient) -> None:
    """Memastikan endpoint regression-a dan regression-b mengembalikan pairs dan typical_duration."""
    res_a = client.get("/api/dashboard/regression-a")
    assert res_a.status_code == 200
    data_a = res_a.get_json()
    if data_a.get("status") != "not_trained":
        assert "pairs" in data_a
        assert isinstance(data_a["pairs"], list)
        assert len(data_a["pairs"]) > 0
        assert "actual" in data_a["pairs"][0]
        assert "predicted" in data_a["pairs"][0]
        assert "typical_duration" in data_a

    res_b = client.get("/api/dashboard/regression-b")
    assert res_b.status_code == 200
    data_b = res_b.get_json()
    if data_b.get("status") != "not_trained":
        assert "pairs" in data_b
        assert isinstance(data_b["pairs"], list)
        assert len(data_b["pairs"]) > 0
        assert "actual" in data_b["pairs"][0]
        assert "predicted" in data_b["pairs"][0]


def test_dashboard_model_a_typical_duration_render(client: FlaskClient, monkeypatch) -> None:
    """Memastikan bila improvement_pct <= 0, kartu Model A menampilkan median dan rentang kuartil."""
    from app.services import dashboard_service

    # Mock get_regression_a_data dengan improvement_pct <= 0
    orig_fn = dashboard_service.get_regression_a_data

    def mock_get_reg_a(*args, **kwargs):
        data = orig_fn(*args, **kwargs)
        if data:
            data = dict(data)
            data["improvement_pct"] = -5.0
            data["typical_duration"] = {"median": 12.5, "q25": 6.0, "q75": 18.0, "iqr": 12.0}
        return data

    monkeypatch.setattr(dashboard_service, "get_regression_a_data", mock_get_reg_a)

    res = client.get("/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Gambaran Tipikal Durasi Data Latih" in html
    assert "12.5 bulan" in html
    assert "6.0" in html and "18.0" in html


def test_dashboard_js_reads_pairs_key() -> None:
    """Memastikan dashboard.js membaca kunci pairs untuk scatter Model A dan B."""
    js_content = Path("app/web/static/js/dashboard.js").read_text(encoding="utf-8")
    assert "resData.pairs" in js_content
    assert "predictions" in js_content
