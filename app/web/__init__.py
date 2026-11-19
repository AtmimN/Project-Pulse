"""Inisialisasi aplikasi Flask untuk ProjectPulse."""
from __future__ import annotations

from typing import Any
from flask import Flask, Response

from app import config
from app.db.connection import init_db
from app.web.routes import main_bp


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    """Application factory untuk menginisialisasi dan mengonfigurasi Flask."""
    app = Flask(__name__)
    app.config.from_object(config.Config)

    if test_config:
        app.config.update(test_config)

    # Inisialisasi basis data jika belum ada
    db_target = app.config.get("DATABASE_PATH")
    init_db(db_target)

    # Daftarkan blueprint tampilan web
    app.register_blueprint(main_bp)

    @app.after_request
    def set_security_headers(response: Response) -> Response:
        """Menambahkan header keamanan esensial pada respons HTTP."""
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    return app


__all__ = ["create_app"]
