"""Pengujian endpoint web dan antarmuka Flask."""
from flask.testing import FlaskClient


def test_index_page(client: FlaskClient) -> None:
    """Memastikan halaman beranda dapat diakses dengan kode status 200."""
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "ProjectPulse" in html
    assert "WAL" in html
    assert "Estimasi Proyek" in html
    assert "Chatbot PM-Bot" in html


def test_security_headers(client: FlaskClient) -> None:
    """Memastikan header keamanan penting disematkan pada setiap respons."""
    response = client.get("/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"


def test_chat_page(client: FlaskClient) -> None:
    """Memastikan halaman chatbot interaktif termuat dengan benar."""
    response = client.get("/chat")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "PM-Bot" in html
    assert "chat-container" in html
    assert "chatMessages" in html


def test_estimate_page(client: FlaskClient) -> None:
    """Memastikan halaman estimasi proyek termuat dengan teks peringatan dan penjelasan M2-rev."""
    response = client.get("/estimasi")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Kalkulator Estimasi Proyek Berdampingan" in html
    assert "estimateForm" in html
    assert "Model A — pola historis repositori GitHub" in html
    assert "pendekatan kontributor kumulatif" in html
    assert "Model A mempelajari korelasi historis, bukan sebab-akibat" in html
    assert "Mengapa Model A dan Model B bisa berlawanan arah?" in html


def test_dashboard_and_api_endpoints(client: FlaskClient) -> None:
    """Memastikan halaman dashboard dan endpoint metrik regresi mengembalikan data valid."""
    resp_dash = client.get("/dashboard")
    assert resp_dash.status_code == 200
    html = resp_dash.get_data(as_text=True)
    assert "Dashboard Analitik" in html
    assert "Model A" in html
    assert "Milestone" in html

    # Endpoint REST API Model A
    resp_a = client.get("/api/dashboard/regression-a")
    assert resp_a.status_code == 200
    data_a = resp_a.get_json()
    assert isinstance(data_a, dict)

    # Endpoint REST API Model B
    resp_b = client.get("/api/dashboard/regression-b")
    assert resp_b.status_code == 200
    data_b = resp_b.get_json()
    assert isinstance(data_b, dict)


def test_placeholder_pages(client: FlaskClient) -> None:
    """Memastikan seluruh menu navigasi belum selesai tetap dapat diakses tanpa error 404."""
    routes = ["/repositori", "/dashboard", "/admin"]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Milestone" in html
