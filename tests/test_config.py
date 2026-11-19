"""Pengujian konfigurasi dan konstanta aplikasi."""
from app import config


def test_config_constants() -> None:
    """Memastikan seluruh konstanta sistem terdefinisi dengan nilai yang sesuai spesifikasi."""
    assert config.MAX_COMMENTS_PER_REPO == 2000
    assert config.BACKFILL_DAYS == 90
    assert config.SNAPSHOT_INTERVAL_DAYS == 7
    assert config.MAX_MONITOR_REPOS == 10
    assert config.MIN_TRAINING_ROWS == 30
    assert config.CLONE_DIR == "instance/clones"
    assert config.COMPARISON_FLAG_RATIO == 2.0
    assert config.MAX_MESSAGE_LEN == 500


def test_config_technical_words_and_logins() -> None:
    """Memastikan kata teknis netral dan bot logins terdefinisi dalam bentuk tuple."""
    assert "bug" in config.TECHNICAL_NEUTRAL_WORDS
    assert "error" in config.TECHNICAL_NEUTRAL_WORDS
    assert "dependabot" in config.IGNORED_LOGINS
    assert "github-actions[bot]" in config.IGNORED_LOGINS


def test_flask_config_class() -> None:
    """Memastikan kelas Flask Config memuat nilai keamanan cookie sesi."""
    assert config.Config.SESSION_COOKIE_HTTPONLY is True
    assert config.Config.SESSION_COOKIE_SAMESITE == "Lax"
