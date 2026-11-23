"""Endpoint REST API untuk data analitik dashboard ProjectPulse."""
from __future__ import annotations

from flask import current_app, jsonify, Response

from app.services import dashboard_service
from app.web.routes import main_bp


@main_bp.route("/api/dashboard/summary")
def api_dashboard_summary() -> tuple[Response, int]:
    """Endpoint REST API untuk ringkasan metrik dashboard."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_dashboard_summary(db_path=db_target)), 200


@main_bp.route("/api/dashboard/sentiment-by-repo")
def api_dashboard_sentiment_by_repo() -> tuple[Response, int]:
    """Endpoint REST API sebaran sentimen per repositori (30 hari)."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_sentiment_by_repo(db_path=db_target)), 200


@main_bp.route("/api/dashboard/sentiment-trend")
def api_dashboard_sentiment_trend() -> tuple[Response, int]:
    """Endpoint REST API tren bulanan indeks sentimen repositori."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_sentiment_trend(db_path=db_target)), 200


@main_bp.route("/api/dashboard/training-data")
def api_dashboard_training_data() -> tuple[Response, int]:
    """Endpoint REST API ringkasan data latih dan alasan pengeluaran."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_training_data_summary(db_path=db_target)), 200


@main_bp.route("/api/dashboard/recent-estimations")
def api_dashboard_recent_estimations() -> tuple[Response, int]:
    """Endpoint REST API 5 estimasi terakhir."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_recent_estimations(limit=5, db_path=db_target)), 200


@main_bp.route("/api/dashboard/recent-alerts")
def api_dashboard_recent_alerts() -> tuple[Response, int]:
    """Endpoint REST API 10 riwayat alert terbaru tanpa data pelanggan."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_recent_alerts(limit=10, db_path=db_target)), 200


@main_bp.route("/api/dashboard/scheduler-status")
def api_dashboard_scheduler_status() -> tuple[Response, int]:
    """Endpoint REST API status eksekusi terakhir dan jadwal penjadwal harian."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_scheduler_status(db_path=db_target)), 200


@main_bp.route("/api/dashboard/duration-benchmark")
def api_dashboard_duration_benchmark() -> tuple[Response, int]:
    """Endpoint REST API benchmark durasi repositori open source."""
    db_target = current_app.config.get("DATABASE_PATH")
    return jsonify(dashboard_service.get_duration_benchmark(db_path=db_target)), 200
