"""Pengujian komprehensif modul chatbot PM-Bot dan endpoint /api/chat."""
from pathlib import Path
from flask.testing import FlaskClient

from app.chatbot.engine import ChatbotEngine, load_intents
from app.chatbot.handlers import HANDLERS, repo_sentiment_handler
from app.db import connection, repos_repo, daily_stats_repo, releases_repo, conversations_repo
from app.services.chat_service import RepoSentimentProvider, process_chat


class FakeRepoSentimentProvider:
    """Provider tiruan untuk menguji handler repo_sentiment secara terisolasi."""

    def __init__(self, repos: list[dict]) -> None:
        self.repos = repos

    def get_repo_sentiment_info(self) -> dict:
        return {"active_repos": self.repos}


def test_greeting_and_intents_matching() -> None:
    """Menguji pengenalan intent sapaan, menu, intent lama, dan intent baru."""
    intents_data = load_intents()
    engine = ChatbotEngine(intents_data=intents_data, threshold=0.45)

    # 1. Sapaan
    res_salam = engine.reply("halo bot")
    assert res_salam["intent"] == "salam"

    # 2. Menu
    res_menu = engine.reply("menu bantuan")
    assert res_menu["intent"] == "menu"

    # 3. Intent lama PM-Bot
    res_fase = engine.reply("tahapan proyek")
    assert res_fase["intent"] == "fase_proyek"

    res_agile = engine.reply("apa itu agile")
    assert res_agile["intent"] == "apa_itu_agile"

    res_pm = engine.reply("tugas project manager")
    assert res_pm["intent"] == "tugas_project_manager"

    res_wbs = engine.reply("contoh wbs")
    assert res_wbs["intent"] == "template_wbs"

    res_tools = engine.reply("rekomendasi tools proyek")
    assert res_tools["intent"] == "rekomendasi_tools"

    # 4. Intent baru ProjectPulse
    res_est = engine.reply("estimasi durasi proyek")
    assert res_est["intent"] == "estimate_project"
    assert "/estimasi" in res_est["reply"]

    res_dash = engine.reply("lihat dashboard")
    assert res_dash["intent"] == "show_dashboard"
    assert "/dashboard" in res_dash["reply"]

    # 5. Pesan tak dikenal -> Fallback
    res_unknown = engine.reply("xyz abc kata tidak jelas 12345")
    assert res_unknown["intent"] is None
    assert len(res_unknown["reply"]) > 0


def test_repo_sentiment_handler_with_data() -> None:
    """Menguji respon dinamis saat repositori pantau memiliki data sentimen dan rilis."""
    fake_repos = [
        {
            "id": 1,
            "full_name": "plankanban/planka",
            "stats": {
                "total_comments": 100,
                "total_positive": 60,
                "total_neutral": 30,
                "total_negative": 10,
                "latest_stat_date": "2026-11-18",
            },
            "latest_release": {
                "tag": "v2.2.0",
                "published_at": "2026-11-12T00:00:00Z",
            },
            "last_updated": "2026-11-18",
        }
    ]
    provider = FakeRepoSentimentProvider(fake_repos)

    # Uji pencocokan nama bagian akhir ("planka")
    jawaban_short = repo_sentiment_handler("sentimen planka", provider)
    assert "plankanban/planka" in jawaban_short
    assert "60% komentar positif" in jawaban_short
    assert "30% netral" in jawaban_short
    assert "10% negatif" in jawaban_short
    assert "100 komentar" in jawaban_short
    assert "v2.2.0" in jawaban_short

    # Uji pencocokan full name ("plankanban/planka")
    jawaban_full = repo_sentiment_handler("bagaimana suasana repo plankanban/planka?", provider)
    assert "plankanban/planka" in jawaban_full
    assert "60% komentar positif" in jawaban_full


def test_repo_sentiment_handler_empty_and_unknown() -> None:
    """Menguji respon saat repositori tidak memiliki komentar atau tidak ditemukan."""
    fake_repos = [
        {
            "id": 1,
            "full_name": "plankanban/planka",
            "stats": {"total_comments": 0},
            "latest_release": None,
        }
    ]
    provider = FakeRepoSentimentProvider(fake_repos)

    # Ada repo, tapi 0 komentar
    jawaban_empty = repo_sentiment_handler("sentimen planka", provider)
    assert "Belum ada data komentar untuk plankanban/planka" in jawaban_empty

    # Repo tidak ada di daftar
    jawaban_unknown = repo_sentiment_handler("sentimen repo-gaib", provider)
    assert "Repositori tidak ditemukan" in jawaban_unknown
    assert "plankanban/planka" in jawaban_unknown


def test_repo_sentiment_integration_with_db(temp_db_path: Path) -> None:
    """Menguji integrasi chat_service membaca data riil dari SQLite."""
    with connection.transaction(temp_db_path) as conn:
        repo_id = repos_repo.add_repo(conn, "pallets/flask", "monitor", active=1)
        daily_stats_repo.upsert_daily_stats(
            conn, repo_id, "2026-11-18", n_comments=20, n_positive=12, n_neutral=6, n_negative=2
        )
        releases_repo.add_release(
            conn, repo_id, 101, "3.1.0", "2026-11-01T10:00:00Z", name="Flask 3.1.0"
        )

    res = process_chat("sentimen flask", "sess-test-1", db_path=temp_db_path)
    assert res["intent"] == "repo_sentiment"
    assert "pallets/flask" in res["reply"]
    assert "60% komentar positif" in res["reply"]
    assert "3.1.0" in res["reply"]


def test_api_chat_validation_and_limits(client: FlaskClient) -> None:
    """Menguji validasi input API chat: kosong, spasi, dan melebihi 500 karakter."""
    # 1. Body kosong
    r_empty_body = client.post("/api/chat", json={})
    assert r_empty_body.status_code == 400

    # 2. Pesan kosong atau whitespace
    r_empty_msg = client.post("/api/chat", json={"message": "   "})
    assert r_empty_msg.status_code == 400
    assert "tidak boleh kosong" in r_empty_msg.get_json()["error"]

    # 3. Pesan > 500 karakter
    panjang_501 = "a" * 501
    r_too_long = client.post("/api/chat", json={"message": panjang_501})
    assert r_too_long.status_code == 400
    assert "melebihi batas" in r_too_long.get_json()["error"]

    # 4. Pesan valid
    r_valid = client.post("/api/chat", json={"message": "halo bot"})
    assert r_valid.status_code == 200
    data = r_valid.get_json()
    assert "reply" in data
    assert data["intent"] == "salam"


def test_conversation_logging(client: FlaskClient, temp_db_path: Path) -> None:
    """Memverifikasi pencatatan log percakapan ke tabel conversation_logs."""
    client.post("/api/chat", json={"message": "apa itu agile"})

    with connection.transaction(temp_db_path) as conn:
        logs = conversations_repo.list_conversations(conn, limit=10)
        assert len(logs) >= 1
        assert logs[0]["message"] == "apa itu agile"
        assert logs[0]["intent"] == "apa_itu_agile"


def test_no_theme_references_in_app() -> None:
    """Memastikan tidak ada rute, tabel, atau konsep tema yang tersisa di app/."""
    app_dir = Path(__file__).resolve().parent.parent / "app"
    
    # Periksa seluruh berkas python di app/
    for py_file in app_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        # Tidak boleh ada route atau fungsi bertema
        assert "/admin/<theme_id>" not in content
        assert "load_themes" not in content
        assert "validate_theme" not in content
