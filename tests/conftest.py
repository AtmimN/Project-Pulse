"""Konfigurasi dan fixture pytest untuk ProjectPulse."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Generator
import pytest
from flask import Flask

from app.web import create_app
from app.db.connection import init_db


@pytest.fixture
def temp_db_path() -> Generator[Path, None, None]:
    """Menyediakan berkas database SQLite sementara untuk pengujian terisolasi."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    
    init_db(tmp_path)
    yield tmp_path

    # Bersihkan berkas setelah pengujian
    for p in (tmp_path, Path(f"{tmp_path}-wal"), Path(f"{tmp_path}-shm")):
        if p.exists():
            try:
                p.unlink()
            except OSError:
                pass


@pytest.fixture
def app(temp_db_path: Path) -> Flask:
    """Fixture aplikasi Flask yang dikonfigurasi dengan database sementara."""
    test_app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(temp_db_path),
            "SECRET_KEY": "test-secret-key",
        }
    )
    return test_app


@pytest.fixture
def client(app: Flask):
    """Fixture test client Flask."""
    return app.test_client()
