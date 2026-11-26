"""Layanan pemrosesan batch data latih GitHub dan pelatihan Model A & B."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pandas as pd

logger = logging.getLogger(__name__)

from app import config
from app.db import connection, repos_repo, training_rows_repo
from app.estimator.benchmark import calculate_duration_benchmark, save_duration_benchmark
from app.estimator.model_a import train_model_a
from app.estimator.model_b import train_model_b
from app.estimator.nasa93 import load_nasa93_dataset
from app.scraper.github_client import GitHubClient, RateLimitError
from app.scraper.repo_metrics import (
    GitRunner,
    calculate_duration_months,
    contributors_until,
    find_first_stable_release_tag,
    first_commit_date,
    kloc_at,
    release_date,
    validate_repo_name,
)

TRAINING_REPOS_PATH: Path = config.BASE_DIR / "data" / "training_repos.json"
DATASET_CSV_PATH: Path = config.BASE_DIR / "data" / "training_dataset.csv"
EXCLUSIONS_CSV_PATH: Path = config.BASE_DIR / "data" / "training_exclusions.csv"


def _resolve_training_tag(clone_dest: Path, runner: GitRunner, manual_tag: str | None) -> str | None:
    """Menentukan tag rilis stabil untuk repositori data latih."""
    if manual_tag:
        return manual_tag
    raw_tags = runner.run(["tag", "--list"], cwd=clone_dest).splitlines()
    tag_entries = []
    for t in raw_tags:
        t_clean = t.strip()
        if t_clean:
            try:
                tag_entries.append((t_clean, release_date(clone_dest, t_clean, runner)))
            except (RuntimeError, ValueError, OSError) as err:
                logger.debug("Lewati tag %s: %s", t_clean, err)
    return find_first_stable_release_tag(tag_entries)


def _extract_git_metrics(
    clone_dest: Path,
    manual_tag: str | None,
    runner: GitRunner,
) -> tuple[str | None, str, str, float, int, float]:
    """Mengekstrak tag rilis, tanggal commit, durasi, kontributor, dan KLOC."""
    chosen_tag = _resolve_training_tag(clone_dest, runner, manual_tag)
    if not chosen_tag:
        return None, "", "", 0.0, 0, 0.0

    first_dt = first_commit_date(clone_dest, runner)
    rel_dt = release_date(clone_dest, chosen_tag, runner)
    dur_months = calculate_duration_months(first_dt, rel_dt)
    n_contrib = contributors_until(clone_dest, chosen_tag, runner)
    kloc = kloc_at(clone_dest, chosen_tag, runner)
    return chosen_tag, first_dt, rel_dt, dur_months, n_contrib, kloc


def _clone_or_fetch_repo(full_name: str, runner: GitRunner) -> Path:
    """Melakukan klon bare atau fetch tag repositori git lokal."""
    dest = Path(config.CLONE_DIR) / f"{full_name.replace('/', '__')}.git"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        runner.run(["clone", "--bare", "--filter=blob:none", f"https://github.com/{full_name}.git", str(dest)])
    else:
        runner.run(["fetch", "--tags", "--prune"], cwd=dest)
    return dest


def _parse_iso_date(dt_str: str) -> datetime:
    """Mengurai string ISO 8601 menjadi objek datetime timezone-aware UTC."""
    cleaned = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_history_gap_exceeded(first_dt_str: str, created_at_str: str) -> bool:
    """Memeriksa apakah commit pertama lebih awal dari tanggal repo melebihi ambang batas."""
    try:
        first_dt = _parse_iso_date(first_dt_str)
        created_dt = _parse_iso_date(created_at_str)
        if first_dt < created_dt:
            gap_days = (created_dt - first_dt).total_seconds() / 86400.0
            gap_months = gap_days / 30.4375
            return gap_months > config.MAX_HISTORY_GAP_MONTHS
    except (ValueError, TypeError, KeyError) as err:
        logger.debug("Gagal memeriksa gap riwayat repositori: %s", err)
    return False


def _fetch_repo_metadata(
    full_name: str, client: GitHubClient, db_path: str | Path | None, repo_id: int,
) -> tuple[str | None, str | None]:
    """Mengambil metadata repositori GitHub dan memeriksa kriteria fork/arsip/privat."""
    try:
        repo_info = client.get_repo(full_name)
        if repo_info.get("fork") or repo_info.get("archived") or repo_info.get("private"):
            _record_exclusion(db_path, repo_id, "fork/arsip/privat")
            return None, "fork/arsip/privat"
        created_at = repo_info.get("created_at")
        if not created_at:
            _record_exclusion(db_path, repo_id, "data pembuatan repositori tidak tersedia")
            return None, "data pembuatan repositori tidak tersedia"
        return created_at, None
    except Exception as err:
        _record_exclusion(db_path, repo_id, f"gagal api: {err}")
        return None, f"gagal api: {err}"


def _validate_repo_metrics(
    tag: str | None, first_dt: str, rel_dt: str, dur: float,
    n_contrib: int, kloc: float, repo_created_at: str | None,
    full_name: str, client: GitHubClient,
) -> tuple[int, str | None]:
    """Memvalidasi aturan kualitas data latih terhadap metrik git dan issue/PR."""
    if not tag:
        return 0, "tidak ada rilis stabil"
    if dur <= 0:
        return 0, "durasi tidak valid"
    if repo_created_at and _is_history_gap_exceeded(first_dt, repo_created_at):
        return 0, "riwayat commit diimpor atau fork"

    q_iss = f"repo:{full_name} is:issue created:<={rel_dt[:10]}"
    q_prs = f"repo:{full_name} is:pr created:<={rel_dt[:10]}"
    n_work = client.search_count(q_iss) + client.search_count(q_prs)
    if n_work <= 0:
        return 0, "jumlah issue+PR nol (data issue tidak tersedia atau riwayat diimpor)"
    if not (1.0 <= dur <= 60.0 and 2 <= n_contrib <= 300 and 1.0 <= kloc <= 500.0):
        return 0, "di luar kriteria numerik"
    return n_work, None


def _check_or_init_repo(
    conn: Any, full_name: str, refresh: bool
) -> tuple[int, bool]:
    """Mengambil atau membuat entri repositori latih dan memeriksa apakah sudah terproses."""
    repo_row = repos_repo.get_by_full_name(conn, full_name)
    repo_id = repo_row["id"] if repo_row else repos_repo.add_repo(conn, full_name, "training")
    already_done = bool(training_rows_repo.get_training_row_by_repo_id(conn, repo_id) and not refresh)
    return repo_id, already_done


def _extract_and_save_training_row(
    clone_dest: Path,
    manual_tag: str | None,
    runner: GitRunner,
    created_at: str | None,
    full_name: str,
    client: GitHubClient,
    db_path: str | Path | None,
    repo_id: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Mengekstrak metrik git, memvalidasi, dan menyimpan baris latih."""
    tag, first_dt, rel_dt, dur, n_c, kloc = _extract_git_metrics(clone_dest, manual_tag, runner)
    n_work, exc_reason = _validate_repo_metrics(tag, first_dt, rel_dt, dur, n_c, kloc, created_at, full_name, client)
    if exc_reason:
        _record_exclusion(db_path, repo_id, exc_reason, created_at)
        return None, {"full_name": full_name, "reason": exc_reason}

    with connection.transaction(db_path) as conn:
        training_rows_repo.add_training_row(
            conn, repo_id, tag, rel_dt, first_dt, dur, n_c, n_work, kloc, 1, None, created_at
        )
    return {
        "full_name": full_name, "release_tag": tag, "duration_months": dur,
        "n_contributors": n_c, "n_work_items": n_work, "kloc": kloc,
    }, None


def _process_single_repo(
    entry: dict[str, Any],
    monitor_repos: list[str],
    client: GitHubClient,
    runner: GitRunner,
    db_path: str | Path | None,
    delete_clones: bool,
    refresh: bool,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Memproses ekstraksi metrik satu repositori latih."""
    full_name = entry.get("full_name", "").strip()
    if not validate_repo_name(full_name):
        return None, {"full_name": full_name, "reason": "format nama tidak valid"}
    if full_name.lower() in monitor_repos:
        return None, {"full_name": full_name, "reason": "beririsan dengan repositori pantau"}

    with connection.transaction(db_path) as conn:
        repo_id, already_done = _check_or_init_repo(conn, full_name, refresh)
        if already_done:
            return None, None

    created_at, err_reason = _fetch_repo_metadata(full_name, client, db_path, repo_id)
    if err_reason:
        return None, {"full_name": full_name, "reason": err_reason}

    clone_dest = _clone_or_fetch_repo(full_name, runner)
    try:
        return _extract_and_save_training_row(
            clone_dest, entry.get("release_tag"), runner, created_at, full_name, client, db_path, repo_id
        )
    finally:
        if delete_clones and clone_dest.exists():
            shutil.rmtree(clone_dest, ignore_errors=True)


def _process_training_repos_loop(
    repos_config: list[dict[str, Any]], monitor_repos: list[str],
    client: GitHubClient, runner: GitRunner, db_path: str | Path | None,
    delete_clones: bool, refresh: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mengeksekusi iterasi pemrosesan setiap entri repositori latih."""
    included, excluded = [], []
    for entry in repos_config:
        try:
            inc, exc = _process_single_repo(entry, monitor_repos, client, runner, db_path, delete_clones, refresh)
            if inc:
                included.append(inc)
            if exc:
                excluded.append(exc)
        except RateLimitError as rl:
            excluded.append({"full_name": entry.get("full_name"), "reason": f"rate limit: {rl}"})
            break
        except Exception as e:
            excluded.append({"full_name": entry.get("full_name"), "reason": f"error: {e}"})
    return included, excluded


def build_training_data(
    refresh: bool = False,
    delete_clones: bool = False,
    github_client: GitHubClient | None = None,
    git_runner: GitRunner | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Membangun dataset latih Model A dari daftar repositori pada training_repos.json."""
    if not TRAINING_REPOS_PATH.exists():
        raise FileNotFoundError(f"Berkas {TRAINING_REPOS_PATH} tidak ditemukan.")

    with open(TRAINING_REPOS_PATH, "r", encoding="utf-8") as f:
        repos_config = json.load(f).get("repos", [])
    if not repos_config:
        return {
            "status": "error",
            "message": "Daftar repositori latih pada data/training_repos.json masih kosong. Silakan isi terlebih dahulu.",
            "n_included": 0, "n_excluded": 0,
        }

    client = github_client or GitHubClient()
    runner = git_runner or GitRunner()
    with connection.transaction(db_path) as conn:
        monitor_repos = [r["full_name"].lower() for r in repos_repo.list_repos(conn, kind="monitor")]
        if refresh:
            training_rows_repo.delete_training_rows(conn)

    results_included, results_excluded = _process_training_repos_loop(
        repos_config, monitor_repos, client, runner, db_path, delete_clones, refresh
    )
    _export_training_csvs(results_included, results_excluded)
    return {
        "status": "success", "n_included": len(results_included),
        "n_excluded": len(results_excluded),
        "warning_insufficient": len(results_included) < config.MIN_TRAINING_ROWS,
    }


def _record_exclusion(
    db_path: str | Path | None,
    repo_id: int,
    reason: str,
    repo_created_at: str | None = None,
) -> None:
    """Mencatat baris pengecualian repositori latih ke tabel training_rows."""
    with connection.transaction(db_path) as conn:
        training_rows_repo.add_training_row(
            conn=conn,
            repo_id=repo_id,
            release_tag=None,
            release_date=None,
            first_commit_date=None,
            duration_months=None,
            n_contributors=None,
            n_work_items=None,
            kloc=None,
            included=0,
            exclusion_reason=reason,
            repo_created_at=repo_created_at,
        )


def _export_training_csvs(included: list[dict[str, Any]], excluded: list[dict[str, Any]]) -> None:
    """Mengekspor berkas data latih training_dataset.csv dan training_exclusions.csv."""
    if included:
        pd.DataFrame(included).to_csv(DATASET_CSV_PATH, index=False)
    if excluded:
        pd.DataFrame(excluded).to_csv(EXCLUSIONS_CSV_PATH, index=False)


def train_models_service(db_path: str | Path | None = None) -> dict[str, Any]:
    """Melatih Model A (data GitHub) dan Model B (NASA93) jika data tersedia."""
    summary: dict[str, Any] = {"model_a": None, "model_b": None, "benchmark_duration": None, "messages": []}

    with connection.transaction(db_path) as conn:
        rows = training_rows_repo.list_training_rows(conn, included_only=True)

    if not rows:
        summary["messages"].append("Data latih Model A belum tersedia di database.")
    else:
        df_a = pd.DataFrame(rows)
        _, metrics_a = train_model_a(df_a)
        summary["model_a"] = metrics_a

        # Bangun benchmark durasi dari baris data latih yang disertakan
        durations = [float(r["duration_months"]) for r in rows if r.get("duration_months") is not None]
        bench_data = calculate_duration_benchmark(durations)
        save_duration_benchmark(bench_data)
        summary["benchmark_duration"] = bench_data

        if len(rows) < config.MIN_TRAINING_ROWS:
            summary["messages"].append(
                f"Peringatan: Jumlah data latih Model A ({len(rows)}) kurang dari {config.MIN_TRAINING_ROWS} baris."
            )

    try:
        df_b = load_nasa93_dataset()
        _, metrics_b = train_model_b(df_b)
        summary["model_b"] = metrics_b
    except Exception as err:
        summary["messages"].append(f"Model B tidak dapat dilatih: {err}")

    return summary
