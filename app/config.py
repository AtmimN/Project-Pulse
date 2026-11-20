"""Modul konfigurasi aplikasi dan konstanta sistem ProjectPulse."""
from __future__ import annotations

import os
from pathlib import Path

# Direktori utama proyek
BASE_DIR: Path = Path(__file__).resolve().parent.parent


def load_env_file(env_path: Path | None = None) -> None:
    """Membaca berkas .env ke dalam os.environ secara aman."""
    target_path = env_path or (BASE_DIR / ".env")
    if not target_path.exists():
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(target_path)
    except ImportError:
        # Fallback sederhana jika python-dotenv belum terpasang
        with open(target_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val


# Muat variabel lingkungan
load_env_file()

# --- Konfigurasi Lingkungan ---
SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-projectpulse-2026")
ADMIN_USERNAME: str = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH: str = os.environ.get("ADMIN_PASSWORD_HASH", "")
DATABASE_PATH: str = os.environ.get("DATABASE_PATH", "instance/projectpulse.db")
GITHUB_TOKEN: str = os.environ.get("GITHUB_TOKEN", "")
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TIMEZONE: str = os.environ.get("TIMEZONE", "Asia/Jakarta")
SCRAPE_HOUR: int = int(os.environ.get("SCRAPE_HOUR", "7"))
SCRAPE_MINUTE: int = int(os.environ.get("SCRAPE_MINUTE", "0"))
DASHBOARD_URL: str = os.environ.get(
    "DASHBOARD_URL", "http://127.0.0.1:5000/dashboard"
)

# --- Konstanta Aplikasi ---
MAX_COMMENTS_PER_REPO: int = 2000
BACKFILL_DAYS: int = 90
SNAPSHOT_INTERVAL_DAYS: int = 7
MAX_MONITOR_REPOS: int = 10
MIN_TRAINING_ROWS: int = 30
MAX_HISTORY_GAP_MONTHS: int = int(os.environ.get("MAX_HISTORY_GAP_MONTHS", "6"))
CLONE_DIR: str = "instance/clones"
COMPARISON_FLAG_RATIO: float = 2.0
MAX_MESSAGE_LEN: int = 500

TECHNICAL_NEUTRAL_WORDS: tuple[str, ...] = (
    "bug", "bugs", "error", "errors", "issue", "issues",
    "fail", "fails", "failed", "failing", "failure",
    "exception", "warning", "warnings", "deprecated"
)

IGNORED_LOGINS: tuple[str, ...] = (
    "dependabot", "dependabot[bot]", "github-actions",
    "github-actions[bot]", "renovate", "renovate[bot]",
    "stale[bot]", "codecov[bot]"
)


class Config:
    """Kelas konfigurasi untuk Flask."""
    SECRET_KEY = SECRET_KEY
    ADMIN_USERNAME = ADMIN_USERNAME
    ADMIN_PASSWORD_HASH = ADMIN_PASSWORD_HASH
    DATABASE_PATH = DATABASE_PATH
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
