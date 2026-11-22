"""Modul rute autentikasi, beranda, intent, dan log percakapan panel admin."""
from __future__ import annotations

import time
import uuid
from typing import Any
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from app import config
from app.db import connection, conversations_repo
from app.services import admin_monitoring_service, admin_service

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _ensure_csrf() -> str:
    """Membuat atau mengambil token CSRF dari sesi pengguna."""
    if "csrf_token" not in session:
        session["csrf_token"] = uuid.uuid4().hex
    return session["csrf_token"]


@admin_bp.before_request
def _admin_auth_and_csrf() -> Any:
    """Memverifikasi sesi login admin dan validitas token CSRF pada form POST."""
    _ensure_csrf()
    if request.endpoint in ("admin.login", "admin.logout", "static"):
        return None

    if not session.get("admin_logged_in"):
        flash("Silakan login terlebih dahulu untuk mengakses panel admin.", "warning")
        return redirect(url_for("admin.login"))

    if request.method == "POST":
        token = request.form.get("csrf_token")
        if not token or token != session.get("csrf_token"):
            flash("Permintaan ditolak: Token CSRF tidak valid atau kedaluwarsa.", "danger")
            return redirect(request.referrer or url_for("admin.index"))
    return None


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """Halaman login admin dengan verifikasi hash dan pembatasan percobaan gagal."""
    if session.get("admin_logged_in"):
        return redirect(url_for("admin.index"))

    lockout = session.get("lockout_until", 0)
    if time.time() < lockout:
        wait_sec = int(lockout - time.time())
        flash(f"Terlalu banyak percobaan gagal. Silakan tunggu {wait_sec} detik.", "danger")
        return render_template("admin/login.html")

    if request.method == "POST":
        u, p = request.form.get("username", "").strip(), request.form.get("password", "")
        if not request.form.get("csrf_token") or request.form.get("csrf_token") != session.get("csrf_token"):
            flash("Token CSRF tidak valid.", "danger")
            return render_template("admin/login.html")

        stored_hash = config.ADMIN_PASSWORD_HASH.strip()
        if not stored_hash:
            flash("ADMIN_PASSWORD_HASH belum dikonfigurasi di berkas .env.", "danger")
            return render_template("admin/login.html")

        if u == config.ADMIN_USERNAME and check_password_hash(stored_hash, p):
            session["admin_logged_in"] = True
            session["failed_attempts"] = 0
            flash("Berhasil masuk ke panel admin ProjectPulse.", "success")
            return redirect(url_for("admin.index"))

        fails = session.get("failed_attempts", 0) + 1
        session["failed_attempts"] = fails
        if fails >= 5:
            session["lockout_until"] = time.time() + 60
            flash("5 kali gagal. Akses ditangguhkan selama 60 detik.", "danger")
        else:
            flash(f"Nama pengguna atau kata sandi salah (percobaan {fails}/5).", "danger")

    return render_template("admin/login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout():
    """Mengakhiri sesi login admin."""
    session.pop("admin_logged_in", None)
    flash("Anda telah berhasil logout dari panel admin.", "info")
    return redirect(url_for("admin.login"))


@admin_bp.route("")
@admin_bp.route("/")
def index():
    """Halaman beranda ringkasan panel admin."""
    db_target = current_app.config.get("DATABASE_PATH")
    repos_data = admin_service.get_repos_admin_data(db_target)
    subs = admin_monitoring_service.get_subscribers_monitoring(db_target)
    return render_template("admin/index.html", repos_data=repos_data, subscribers_count=len(subs))


@admin_bp.route("/intents", methods=["GET"])
def intents():
    """Halaman kelola intent chatbot."""
    return render_template("admin/intents.html", intents=admin_service.list_intents_service())


@admin_bp.route("/intents/add", methods=["POST"])
def add_intent():
    """Menambahkan intent baru."""
    tag = request.form.get("tag", "").strip()
    pola = request.form.get("patterns", "").splitlines()
    resp = request.form.get("responses", "").splitlines()
    try:
        admin_service.add_intent_service(tag, pola, resp)
        flash(f"Intent '{tag}' berhasil ditambahkan.", "success")
    except Exception as ex:
        flash(f"Gagal menambahkan intent: {ex}", "danger")
    return redirect(url_for("admin.intents"))


@admin_bp.route("/intents/edit", methods=["POST"])
def edit_intent():
    """Mengubah pola dan jawaban intent."""
    tag = request.form.get("tag", "").strip()
    pola = request.form.get("patterns", "").splitlines()
    resp = request.form.get("responses", "").splitlines()
    try:
        admin_service.update_intent_service(tag, pola, resp)
        flash(f"Intent '{tag}' berhasil diperbarui.", "success")
    except Exception as ex:
        flash(f"Gagal memperbarui intent: {ex}", "danger")
    return redirect(url_for("admin.intents"))


@admin_bp.route("/intents/delete", methods=["POST"])
def delete_intent():
    """Menghapus intent non-handler."""
    tag = request.form.get("tag", "").strip()
    try:
        admin_service.delete_intent_service(tag)
        flash(f"Intent '{tag}' berhasil dihapus.", "success")
    except Exception as ex:
        flash(f"Gagal menghapus intent: {ex}", "danger")
    return redirect(url_for("admin.intents"))


@admin_bp.route("/logs")
def logs():
    """Halaman log percakapan chatbot dengan filter intent."""
    db_target = current_app.config.get("DATABASE_PATH")
    intent_f = request.args.get("intent", "").strip() or None
    page = max(1, int(request.args.get("page", 1)))
    limit = 20
    offset = (page - 1) * limit
    with connection.transaction(db_target) as conn:
        convs = conversations_repo.list_conversations(conn, limit=limit, offset=offset, intent_filter=intent_f)
    return render_template("admin/logs.html", logs=convs, page=page, intent_filter=intent_f or "")
