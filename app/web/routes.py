"""Modul rute tampilan web utama untuk ProjectPulse."""
from __future__ import annotations

from flask import Blueprint, current_app, render_template

from app import config
from app.db.connection import get_connection

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index() -> str:
    """Menampilkan halaman beranda aplikasi dengan informasi status sistem."""
    journal_mode = "unknown"
    foreign_keys = 0
    try:
        with get_connection() as conn:
            row_jm = conn.execute("PRAGMA journal_mode;").fetchone()
            if row_jm:
                journal_mode = row_jm[0]
            row_fk = conn.execute("PRAGMA foreign_keys;").fetchone()
            if row_fk:
                foreign_keys = int(row_fk[0])
    except Exception:
        journal_mode = "error"

    return render_template(
        "index.html",
        db_path=config.DATABASE_PATH,
        journal_mode=journal_mode,
        foreign_keys=foreign_keys,
        timezone=config.TIMEZONE,
    )


@main_bp.route("/chat")
def chat_page() -> str:
    """Menampilkan halaman chatbot (disediakan pada Milestone M1)."""
    return render_template(
        "placeholder.html",
        title="Chatbot PM-Bot",
        description="Fitur chatbot interaktif berbasis rule-based dan integrasi sentimen repositori pantau.",
        milestone="Milestone M1",
    )


@main_bp.route("/estimasi")
def estimate_page() -> str:
    """Menampilkan halaman estimasi regresi (disediakan pada Milestone M2)."""
    return render_template(
        "placeholder.html",
        title="Estimasi Durasi Proyek",
        description="Dua model regresi linear berdampingan (Data Repositori GitHub & NASA93).",
        milestone="Milestone M2",
    )


@main_bp.route("/repositori")
def repos_page() -> str:
    """Menampilkan halaman Pulse Repositori (disediakan pada Milestone M3/M6)."""
    return render_template(
        "placeholder.html",
        title="Pulse Repositori",
        description="Analisis sentimen komentar issue dan review PR terkini.",
        milestone="Milestone M3",
    )


@main_bp.route("/dashboard")
def dashboard_page() -> str:
    """Menampilkan halaman dashboard analitik (disediakan pada Milestone M6)."""
    return render_template(
        "placeholder.html",
        title="Dashboard Visual Chart.js",
        description="Visualisasi komprehensif metrik sentimen, regresi, dan status penjadwal.",
        milestone="Milestone M6",
    )


@main_bp.route("/admin")
def admin_page() -> str:
    """Menampilkan halaman panel admin (disediakan pada Milestone M6)."""
    return render_template(
        "placeholder.html",
        title="Panel Admin ProjectPulse",
        description="Pengelolaan intent chatbot, repositori pantau, dan pemantauan sistem.",
        milestone="Milestone M6",
    )
