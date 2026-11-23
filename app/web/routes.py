"""Modul rute tampilan web utama untuk ProjectPulse."""
from __future__ import annotations

import uuid
from flask import Blueprint, current_app, jsonify, render_template, request, session, Response

from app import config
from app.chatbot.engine import load_intents
from app.db.connection import get_connection
from app.db import repos_repo
from app.services import chat_service, dashboard_service, estimate_service, pulse_service

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
        return jsonify({"error": f"Panjang pesan melebihi batas {config.MAX_MESSAGE_LEN} karakter."}), 400

    sid = _get_session_id()
    db_target = current_app.config.get("DATABASE_PATH")
    try:
        hasil = chat_service.process_chat(message=pesan, session_id=sid, db_path=db_target)
        return jsonify({"reply": hasil["reply"], "intent": hasil["intent"]}), 200
    except ValueError as val_err:
        return jsonify({"error": str(val_err)}), 400


@main_bp.route("/estimasi")
def estimate_page() -> str:
    """Menampilkan halaman kalkulator estimasi dua model berdampingan."""
    db_target = current_app.config.get("DATABASE_PATH")
    try:
        with get_connection(db_target) as conn:
            monitor_repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
    except Exception:
        monitor_repos = []

    return render_template("estimate.html", monitor_repos=monitor_repos)


@main_bp.route("/api/estimate/prefill")
def api_estimate_prefill() -> tuple[Response, int]:
    """Endpoint untuk mengambil nilai awal metrik dari snapshot repositori pantau (now)."""
    repo = request.args.get("repo", "").strip()
    as_of = request.args.get("as_of", "now").strip()
    if not repo:
        return jsonify({"error": "invalid_repo", "pesan": "Parameter query 'repo' wajib disertakan."}), 400

    from app.scraper.repo_metrics import validate_repo_name
    if not validate_repo_name(repo):
        return jsonify({"error": "invalid_repo", "pesan": "Nama repositori tidak valid."}), 400

    if as_of != "now":
        return jsonify({"error": "invalid_as_of", "pesan": "Hanya snapshot 'now' yang didukung untuk prefill."}), 400

    db_target = current_app.config.get("DATABASE_PATH")
    try:
        prefill_data = estimate_service.get_prefill_data(repo, as_of="now", db_path=db_target)
        return jsonify(prefill_data), 200
    except LookupError as lk_err:
        return jsonify({"error": "snapshot_tidak_tersedia", "pesan": str(lk_err)}), 404
    except ValueError as err:
        return jsonify({"error": "invalid_repo", "pesan": str(err)}), 400


@main_bp.route("/api/estimate", methods=["POST"])
def api_estimate() -> tuple[Response, int]:
    """Endpoint REST API untuk menghitung estimasi Model A dan Model B."""
    payload = request.get_json(silent=True)
    if not payload or not isinstance(payload, dict):
        return jsonify({"error": "Permintaan harus berupa JSON valid."}), 400

    db_target = current_app.config.get("DATABASE_PATH")
    try:
        hasil = estimate_service.calculate_estimation(payload, db_path=db_target)
        return jsonify(hasil), 200
    except ValueError as val_err:
        return jsonify({"error": str(val_err)}), 400


@main_bp.route("/repositori")
def repos_page() -> str:
    """Menampilkan halaman Pulse Repositori (analisis sentimen dan komentar)."""
    db_target = current_app.config.get("DATABASE_PATH")
    repo_id = request.args.get("repo", type=int)
    page = max(1, request.args.get("page", default=1, type=int))
    sentiment_filter = request.args.get("filter", "").strip() or None
    data = pulse_service.get_pulse_data(repo_id, page, sentiment_filter, db_path=db_target)
    return render_template("pulse.html", **data)


@main_bp.route("/dashboard")
def dashboard_page() -> str:
    """Menampilkan halaman dashboard analitik, grafik Chart.js, dan metrik regresi."""
    db_target = current_app.config.get("DATABASE_PATH")
    metrics_a = dashboard_service.get_regression_a_data(db_path=db_target)
    metrics_b = dashboard_service.get_regression_b_data()
    duration_benchmark = dashboard_service.get_duration_benchmark(db_path=db_target)
    summary = dashboard_service.get_dashboard_summary(db_path=db_target)
    training_data = dashboard_service.get_training_data_summary(db_path=db_target)
    recent_alerts = dashboard_service.get_recent_alerts(limit=10, db_path=db_target)
    scheduler_status = dashboard_service.get_scheduler_status(db_path=db_target)
    return render_template(
        "dashboard.html",
        metrics_a=metrics_a,
        metrics_b=metrics_b,
        duration_benchmark=duration_benchmark,
        summary=summary,
        training_data=training_data,
        recent_alerts=recent_alerts,
        scheduler_status=scheduler_status,
    )


@main_bp.route("/api/dashboard/regression-a")
def api_dashboard_regression_a() -> tuple[Response, int]:
    """Endpoint REST API metrik dan diagnostik Model A untuk dashboard."""
    db_target = current_app.config.get("DATABASE_PATH")
    data = dashboard_service.get_regression_a_data(db_path=db_target)
    if not data:
        return jsonify({"status": "not_trained", "message": "Model A belum dilatih."}), 200
    return jsonify(data), 200


@main_bp.route("/api/dashboard/regression-b")
def api_dashboard_regression_b() -> tuple[Response, int]:
    """Endpoint REST API metrik Model B untuk dashboard."""
    data = dashboard_service.get_regression_b_data()
    if not data:
        return jsonify({"status": "not_trained", "message": "Model B belum dilatih."}), 200
    return jsonify(data), 200


@main_bp.route("/kesehatan")
def health_page() -> str:
    """Menampilkan halaman Kartu Kesehatan Repositori (daftar atau detail per repositori)."""
    from app.services import health_service
    db_target = current_app.config.get("DATABASE_PATH")
    repo_param = request.args.get("repo", "").strip()

    if repo_param:
        detail = health_service.get_repo_health_detail(repo_param, db_path=db_target)
        return render_template("health.html", mode="detail", repo_name=repo_param, detail=detail)

    repos_health = health_service.get_all_repos_health(db_path=db_target)
    return render_template("health.html", mode="list", repos_health=repos_health)


@main_bp.route("/api/health")
def api_health() -> tuple[Response, int]:
    """Endpoint REST API kartu kesehatan repositori."""
    from app.services import health_service
    repo_param = request.args.get("repo", "").strip()
    if not repo_param:
        return jsonify({"error": "invalid_repo", "pesan": "Parameter query 'repo' wajib disertakan."}), 400

    from app.scraper.repo_metrics import validate_repo_name
    if not validate_repo_name(repo_param):
        return jsonify({"error": "invalid_repo", "pesan": "Nama repositori tidak valid."}), 400

    db_target = current_app.config.get("DATABASE_PATH")
    detail = health_service.get_repo_health_detail(repo_param, db_path=db_target)
    if not detail:
        return jsonify({"error": "repo_not_found", "pesan": f"Repositori '{repo_param}' tidak ditemukan."}), 404

    return jsonify(detail), 200


# Impor endpoint API dashboard tambahan agar terdaftar di main_bp
import app.web.dashboard_api  # noqa: E402, F401
