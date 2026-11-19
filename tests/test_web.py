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


def test_placeholder_pages(client: FlaskClient) -> None:
    """Memastikan seluruh menu navigasi dapat diakses tanpa error 404."""
    routes = ["/chat", "/estimasi", "/repositori", "/dashboard", "/admin"]
    for route in routes:
        response = client.get(route)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "Milestone" in html
