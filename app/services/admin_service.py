"""Layanan pengelolaan intent, repositori, dan scraping manual di panel admin."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app import config
from app.chatbot.engine import DEFAULT_INTENTS_PATH, load_intents
from app.db import connection, repos_repo
from app.services import scrape_service

TRAINING_REPOS_PATH = config.BASE_DIR / "data" / "training_repos.json"


def list_intents_service() -> list[dict[str, Any]]:
    """Mengambil seluruh daftar intent chatbot."""
    data = load_intents()
    return data.get("intents", [])


def save_intents_file(data: dict[str, Any]) -> None:
    """Menyimpan data intents kembali ke berkas JSON."""
    with open(DEFAULT_INTENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_intent_service(tag: str, patterns: list[str], responses: list[str]) -> None:
    """Menambahkan intent baru ke berkas intents.json."""
    tag_clean = tag.strip().lower()
    if not tag_clean:
        raise ValueError("Tag intent tidak boleh kosong.")
    data = load_intents()
    for it in data.get("intents", []):
        if it["tag"].lower() == tag_clean:
            raise ValueError(f"Intent dengan tag '{tag_clean}' sudah ada.")
    data["intents"].append({
        "tag": tag_clean,
        "patterns": [p.strip() for p in patterns if p.strip()],
        "responses": [r.strip() for r in responses if r.strip()],
    })
    save_intents_file(data)


def update_intent_service(tag: str, patterns: list[str], responses: list[str]) -> None:
    """Memperbarui pola dan jawaban intent (mempertahankan handler jika ada)."""
    data = load_intents()
    found = False
    for it in data.get("intents", []):
        if it["tag"].lower() == tag.strip().lower():
            it["patterns"] = [p.strip() for p in patterns if p.strip()]
            it["responses"] = [r.strip() for r in responses if r.strip()]
            found = True
            break
    if not found:
        raise ValueError(f"Intent '{tag}' tidak ditemukan.")
    save_intents_file(data)


def delete_intent_service(tag: str) -> None:
    """Menghapus intent statis (menolak penghapusan intent dinamis/handler)."""
    data = load_intents()
    intents = data.get("intents", [])
    target = next((it for it in intents if it["tag"].lower() == tag.strip().lower()), None)
    if not target:
        raise ValueError(f"Intent '{tag}' tidak ditemukan.")
    if target.get("handler"):
        raise ValueError("Intent bertanda handler (dinamis) tidak boleh dihapus.")
    data["intents"] = [it for it in intents if it["tag"].lower() != tag.strip().lower()]
    save_intents_file(data)


def get_repos_admin_data(db_path: str | Path | None = None) -> dict[str, Any]:
    """Mengambil status repositori pantau dan tampilan daftar repositori latih."""
    with connection.transaction(db_path) as conn:
        monitor_repos = repos_repo.list_repos(conn, kind="monitor")
        q_snap = "SELECT repo_id, MAX(snapshot_at) as last_snap FROM repo_snapshots GROUP BY repo_id"
        snaps = {r["repo_id"]: r["last_snap"] for r in conn.execute(q_snap).fetchall()}
        for r in monitor_repos:
            r["last_snapshot"] = snaps.get(r["id"], "-")

        training_rows = conn.execute(
            "SELECT r.full_name, t.included, t.exclusion_reason, t.duration_months, t.kloc "
            "FROM training_rows t JOIN repos r ON t.repo_id = r.id"
        ).fetchall()
        rows_by_name = {tr["full_name"]: dict(tr) for tr in training_rows}

    training_specs = []
    if TRAINING_REPOS_PATH.exists():
        try:
            with open(TRAINING_REPOS_PATH, "r", encoding="utf-8") as f:
                t_json = json.load(f)
                for item in t_json.get("repos", []):
                    fn = item["full_name"]
                    spec = {"full_name": fn, "release_tag": item.get("release_tag")}
                    spec.update(rows_by_name.get(fn, {"included": "-", "exclusion_reason": "Belum diproses"}))
                    training_specs.append(spec)
        except Exception:
            pass

    monitor_names = {r["full_name"].lower() for r in monitor_repos}
    training_names = {s["full_name"].lower() for s in training_specs}
    duplicates = list(monitor_names.intersection(training_names))

    return {
        "monitor_repos": monitor_repos,
        "training_specs": training_specs,
        "duplicate_warning": duplicates,
        "max_monitor_repos": config.MAX_MONITOR_REPOS,
    }


def add_monitor_repo_admin(full_name: str, db_path: str | Path | None = None) -> None:
    """Menambahkan repositori pantau baru dengan validasi format dan kuota."""
    fn = full_name.strip()
    if "/" not in fn or len(fn.split("/")) != 2:
        raise ValueError("Format repositori harus 'pemilik/nama'.")
    with connection.transaction(db_path) as conn:
        existing = repos_repo.list_repos(conn, kind="monitor")
        if len(existing) >= config.MAX_MONITOR_REPOS:
            raise ValueError(f"Batas maksimal repositori pantau ({config.MAX_MONITOR_REPOS}) telah tercapai.")
        if any(r["full_name"].lower() == fn.lower() for r in existing):
            raise ValueError(f"Repositori '{fn}' sudah terdaftar.")
        repos_repo.add_repo(conn, fn, kind="monitor", active=1)


def is_scraping_running(db_path: str | Path | None = None) -> bool:
    """Memeriksa apakah ada proses scraping yang sedang berlangsung."""
    with connection.transaction(db_path) as conn:
        q = "SELECT id FROM job_runs WHERE job_name = 'scrape' AND status = 'berjalan' LIMIT 1"
        return conn.execute(q).fetchone() is not None


def run_admin_scrape(db_path: str | Path | None = None) -> dict[str, Any]:
    """Menjalankan scraping manual dan mengembalikan ringkasan eksekusi."""
    if is_scraping_running(db_path):
        raise ValueError("Scraping sedang berjalan di latar belakang. Silakan tunggu.")
    return scrape_service.scrape_all_monitor_repos(db_path=db_path, trigger="manual")
