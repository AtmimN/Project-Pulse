"""Titik masuk antarmuka baris perintah (CLI): python -m app.cli <perintah>."""
from __future__ import annotations

import argparse
import sys
from app.db.connection import init_db
from app.services.training_service import build_training_data, train_models_service
from app.services.snapshot_service import snapshot_all_monitor_repos
from app.services.scrape_service import scrape_all_monitor_repos
from app.services.sentiment_service import (
    export_label_sample,
    rescore_comments_service,
    validate_sentiment_service,
)


def cmd_init_db(args: argparse.Namespace) -> None:
    """Menginisialisasi skema basis data SQLite dalam mode WAL."""
    print("Menginisialisasi basis data ProjectPulse...")
    init_db()
    print("Basis data berhasil diinisialisasi dalam mode WAL.")


def cmd_build_training_data(args: argparse.Namespace) -> None:
    """Membangun dataset latih Model A dari training_repos.json."""
    print("Membangun data latih Model A...")
    refresh = bool(getattr(args, "refresh", False))
    delete_clones = bool(getattr(args, "delete_clones", False))
    res = build_training_data(refresh=refresh, delete_clones=delete_clones)
    if res.get("status") == "error":
        print(f"Error: {res.get('message')}")
        return
    print(f"Selesai: {res['n_included']} repositori disertakan, {res['n_excluded']} dikeluarkan.")
    if res.get("warning_insufficient"):
        print("Peringatan: Jumlah data latih kurang dari batas MIN_TRAINING_ROWS.")


def cmd_train_models(args: argparse.Namespace) -> None:
    """Melatih Model A (data GitHub) dan Model B (NASA93)."""
    print("Melatih model regresi...")
    summary = train_models_service()
    if summary.get("model_a"):
        m_a = summary["model_a"]
        print(f"Model A berhasil dilatih ({m_a['variant']}): Test R2 = {m_a['test_r2']}, MAE = {m_a['test_mae']} bulan.")
    if summary.get("model_b"):
        m_b = summary["model_b"]
        print(f"Model B berhasil dilatih: Test R2 orig = {m_b['test_r2_orig']}, MAE = {m_b['test_mae_person_months']} person-bulan.")
    for msg in summary.get("messages", []):
        print(f"Catatan: {msg}")


def cmd_snapshot_repos(args: argparse.Namespace) -> None:
    """Memperbarui metrik snapshot repositori pantau."""
    print("Memperbarui snapshot repositori pantau...")
    results = snapshot_all_monitor_repos()
    print(f"Selesai memproses {len(results)} repositori pantau.")


def cmd_scrape_repos(args: argparse.Namespace) -> None:
    """Menjalankan scraping incremental komentar dan rilis repositori pantau."""
    print("Menjalankan scraping repositori pantau...")
    res = scrape_all_monitor_repos()
    print(f"Selesai (Status: {res['status']}): {res['new_comments']} komentar baru, {res['new_releases']} rilis baru.")
    for r in res.get("results", []):
        print(f" - {r['full_name']}: {r['status']} ({r['new_comments']} komentar, {r['new_releases']} rilis)")


def cmd_export_label_sample(args: argparse.Namespace) -> None:
    """Mengekspor sampel komentar untuk pelabelan manual."""
    n = getattr(args, "n", 200)
    print(f"Mengekspor {n} sampel komentar...")
    count = export_label_sample(n=n)
    print(f"Berhasil mengekspor {count} baris ke data/labels/sample_to_label.csv.")


def cmd_validate_sentiment(args: argparse.Namespace) -> None:
    """Memvalidasi model sentimen terhadap berkas label manual."""
    print("Memvalidasi model sentimen...")
    res = validate_sentiment_service()
    if not res.get("validated"):
        print(f"Info: {res.get('message')}")
        return
    v = res["vader"]
    print(f"Hasil VADER ({res['n_samples']} sampel): Akurasi = {v['accuracy']}, Macro-F1 = {v['macro_f1']}")
    if res.get("classifier"):
        c = res["classifier"]
        print(f"Hasil Classifier: Akurasi = {c['accuracy']}, Macro-F1 = {c['macro_f1']}")


def cmd_rescore(args: argparse.Namespace) -> None:
    """Menghitung ulang label sentimen pada tabel comments."""
    print("Menghitung ulang sentimen pada seluruh komentar...")
    res = rescore_comments_service()
    print(f"Selesai: {res['comments_rescored']} komentar berhasil dihitung ulang (Metode: {res['method']}).")


def cmd_stub(command_name: str, milestone: str) -> None:
    """Menampilkan informasi bahwa perintah akan diimplementasikan pada milestone terkait."""
    print(f"Perintah '{command_name}' akan diimplementasikan pada {milestone}.")


def main() -> None:
    """Parser argumen CLI ProjectPulse."""
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="Perintah pemrosesan batch dan utilitas sistem ProjectPulse.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Perintah yang tersedia")

    subparsers.add_parser("init-db", help="Inisialisasi tabel basis data mode WAL")

    p_btd = subparsers.add_parser("build-training-data", help="Membangun data latih Model A")
    p_btd.add_argument("--refresh", action="store_true", help="Perbarui data yang sudah ada")
    p_btd.add_argument("--delete-clones", action="store_true", help="Hapus klon sementara")

    subparsers.add_parser("train-models", help="Melatih Model A dan Model B")
    subparsers.add_parser("snapshot-repos", help="Memperbarui metrik snapshot repositori pantau")
    subparsers.add_parser("scrape-repos", help="Scraping incremental komentar dan rilis repositori pantau")

    p_els = subparsers.add_parser("export-label-sample", help="Ekspor sampel komentar untuk pelabelan manual")
    p_els.add_argument("--n", type=int, default=200, help="Jumlah sampel")

    subparsers.add_parser("validate-sentiment", help="Validasi akurasi sentimen terhadap label manual")
    subparsers.add_parser("rescore", help="Hitung ulang label sentimen komentar tersimpan")

    p_ba = subparsers.add_parser("backtest-alerts", help="Uji aturan alert pada data historis")
    p_ba.add_argument("--days", type=int, default=60, help="Jumlah hari ke belakang")
    p_ba.add_argument("--repo", type=str, help="Nama repositori tertentu")

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit(0)

    dispatch_command(args)


def dispatch_command(args: argparse.Namespace) -> None:
    """Mengarahkan eksekusi ke fungsi handler perintah yang sesuai."""
    sub = args.subcommand
    handlers = {
        "init-db": cmd_init_db,
        "build-training-data": cmd_build_training_data,
        "train-models": cmd_train_models,
        "snapshot-repos": cmd_snapshot_repos,
        "scrape-repos": cmd_scrape_repos,
        "export-label-sample": cmd_export_label_sample,
        "validate-sentiment": cmd_validate_sentiment,
        "rescore": cmd_rescore,
    }
    if sub in handlers:
        handlers[sub](args)
    elif sub == "backtest-alerts":
        cmd_stub(sub, "Milestone M4")
    else:
        print(f"Perintah tidak dikenal: {sub}")
        sys.exit(1)


if __name__ == "__main__":
    main()
