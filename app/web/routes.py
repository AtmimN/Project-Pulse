"""Modul rute tampilan web utama untuk ProjectPulse."""
from __future__ import annotations

import uuid
from flask import Blueprint, current_app, jsonify, render_template, request, session, Response

from app import config
from app.chatbot.engine import load_intents
from app.db.connection import get_connection
from app.services import chat_service

main_bp = Blueprint("main", __name__)


def _get_session_id() -> str:
    """Mengambil atau membuat ID sesi acak pengunjung."""
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


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
    """Menampilkan halaman interaktif chatbot PM-Bot."""
    _get_session_id()
    intents_data = load_intents()
    return render_template(
        "chat.html",
        bot_name=intents_data.get("bot_name", "PM-Bot"),
        greeting=intents_data.get("greeting", "Halo! Ada yang bisa saya bantu?"),
        suggestions=intents_data.get("suggestions", []),
    )


@main_bp.route("/api/chat", methods=["POST"])
def api_chat() -> tuple[Response, int]:
    """Endpoint REST API untuk mengirim pesan ke chatbot."""
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict) or "message" not in data:
        return jsonify({"error": "Permintaan harus berupa JSON dengan field 'message'."}), 400

    pesan = data.get("message", "")
    if not isinstance(pesan, str) or not pesan.strip():
        return jsonify({"error": "Pesan tidak boleh kosong."}), 400

    if len(pesan) > config.MAX_MESSAGE_LEN:
        return jsonify(
            {"error": f"Panjang pesan melebihi batas {config.MAX_MESSAGE_LEN} karakter."}
        ), 400

    sid = _get_session_id()
    db_target = current_app.config.get("DATABASE_PATH")

    try:
        hasil = chat_service.process_chat(
            message=pesan,
            session_id=sid,
            db_path=db_target,
        )
        return jsonify({"reply": hasil["reply"], "intent": hasil["intent"]}), 200
    except ValueError as val_err:
        return jsonify({"error": str(val_err)}), 400


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
