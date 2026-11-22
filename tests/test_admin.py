"""Pengujian fungsionalitas panel admin, otentikasi, CSRF, dan manajemen data (M6)."""
from __future__ import annotations

import json
from pathlib import Path
from flask.testing import FlaskClient
from werkzeug.security import generate_password_hash

from app import config
from app.db import connection, repos_repo, subscribers_repo


def _login_admin(client: FlaskClient) -> str:
    """Helper untuk melakukan login admin dan mengembalikan token CSRF dari sesi."""
    with client.session_transaction() as sess:
        sess["admin_logged_in"] = True
        sess["csrf_token"] = "valid_test_csrf_token"
    return "valid_test_csrf_token"


def test_admin_auth_redirects(client: FlaskClient) -> None:
    """Memastikan rute admin tanpa sesi login dialihkan ke halaman login."""
    routes = ["/admin", "/admin/intents", "/admin/logs", "/admin/repositori", "/admin/pemantauan", "/admin/pengaturan-alert"]
    for r in routes:
        res = client.get(r)
        assert res.status_code == 302
        assert "/admin/login" in res.headers.get("Location", "")


def test_admin_login_success_and_logout(client: FlaskClient, monkeypatch) -> None:
    """Menguji alur login berhasil dan logout menggunakan hash password."""
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", generate_password_hash("rahasia123"))
    monkeypatch.setattr(config, "ADMIN_USERNAME", "admin")

    with client.session_transaction() as sess:
        sess["csrf_token"] = "test_csrf"

    res = client.post("/admin/login", data={"username": "admin", "password": "rahasia123", "csrf_token": "test_csrf"}, follow_redirects=True)
    assert res.status_code == 200
    assert "Ringkasan Panel Administrator" in res.get_data(as_text=True)

    # Logout
    res_out = client.post("/admin/logout", data={"csrf_token": "test_csrf"}, follow_redirects=True)
    assert res_out.status_code == 200
    assert "Login Panel Admin" in res_out.get_data(as_text=True)


def test_admin_csrf_protection(client: FlaskClient) -> None:
    """Memastikan form POST tanpa token CSRF valid ditolak."""
    _login_admin(client)
    res = client.post("/admin/intents/add", data={"tag": "hacker_tag", "csrf_token": "wrong_token"}, follow_redirects=True)
    assert res.status_code == 200
    assert "CSRF tidak valid" in res.get_data(as_text=True)


def test_admin_intents_management_and_handler_safety(client: FlaskClient) -> None:
    """Menguji penambahan, pengubahan, dan proteksi penghapusan intent dinamis."""
    csrf = _login_admin(client)

    # Tambah intent baru
    res_add = client.post("/admin/intents/add", data={
        "tag": "test_tag_m6",
        "patterns": "tanya sesuatu\napakah ini bekerja",
        "responses": "Ya tentu saja ini bekerja",
        "csrf_token": csrf,
    }, follow_redirects=True)
    assert res_add.status_code == 200
    assert "test_tag_m6" in res_add.get_data(as_text=True)

    # Coba hapus intent dinamis yang memiliki handler (misal repo_sentiment)
    res_del_handler = client.post("/admin/intents/delete", data={"tag": "repo_sentiment", "csrf_token": csrf}, follow_redirects=True)
    assert res_del_handler.status_code == 200
    assert "tidak boleh dihapus" in res_del_handler.get_data(as_text=True)

    # Hapus intent statis yang baru dibuat
    res_del = client.post("/admin/intents/delete", data={"tag": "test_tag_m6", "csrf_token": csrf}, follow_redirects=True)
    assert res_del.status_code == 200
    assert "berhasil dihapus" in res_del.get_data(as_text=True)


def test_admin_repos_and_monitoring(client: FlaskClient, temp_db_path: Path) -> None:
    """Menguji penambahan repo pantau, toggle aktif, penyamaran chat_id, dan kata kunci."""
    csrf = _login_admin(client)

    # Tambah repositori pantau
    res_repo = client.post("/admin/repositori/add", data={"full_name": "owner/new-repo", "csrf_token": csrf}, follow_redirects=True)
    assert res_repo.status_code == 200
    assert "owner/new-repo" in res_repo.get_data(as_text=True)

    # Tambah subscriber & cek penyamaran chat_id
    with connection.transaction(temp_db_path) as conn:
        subscribers_repo.add_or_update_subscriber(conn, 12345678)

    res_mon = client.get("/admin/pemantauan")
    assert res_mon.status_code == 200
    html_mon = res_mon.get_data(as_text=True)
    assert "12••••78" in html_mon
    assert "12345678" not in html_mon  # chat_id asli tidak boleh bocor di antarmuka

    # Tambah & hapus kata kunci
    res_kw = client.post("/admin/pengaturan-alert/keywords/add", data={"word": "critical", "csrf_token": csrf}, follow_redirects=True)
    assert res_kw.status_code == 200
    assert "critical" in res_kw.get_data(as_text=True)
