"""Layanan pemrosesan batch data latih GitHub dan pelatihan Model A & B."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
import pandas as pd

from app import config
from app.db import connection, repos_repo, training_rows_repo
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


def _extract_git_metrics(
    clone_dest: Path,
    manual_tag: str | None,
    runner: GitRunner,
) -> tuple[str | None, str, str, float, int, float]:
    """Mengekstrak tag rilis, tanggal commit, durasi, kontributor, dan KLOC."""
    chosen_tag = manual_tag
    if not chosen_tag:
        raw_tags = runner.run(["tag", "--list"], cwd=clone_dest).splitlines()
        tag_entries = []
        for t in raw_tags:
            t_clean = t.strip()
            if t_clean:
                try:
                    c_dt = release_date(clone_dest, t_clean, runner)
                    tag_entries.append((t_clean, c_dt))
                except Exception:
                    pass
        chosen_tag = find_first_stable_release_tag(tag_entries)

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
    manual_tag = entry.get("release_tag")

    if not validate_repo_name(full_name):
        return None, {"full_name": full_name, "reason": "format nama tidak valid"}

    if full_name.lower() in monitor_repos:
        return None, {"full_name": full_name, "reason": "beririsan dengan repositori pantau"}

    with connection.transaction(db_path) as conn:
        repo_row = repos_repo.get_by_full_name(conn, full_name)
        repo_id = repo_row["id"] if repo_row else repos_repo.add_repo(conn, full_name, "training")
        existing = training_rows_repo.get_training_row_by_repo_id(conn, repo_id)
        if existing and not refresh:
            return None, None

    try:
        repo_info = client.get_repo(full_name)
        if repo_info.get("fork") or repo_info.get("archived") or repo_info.get("private"):
            _record_exclusion(db_path, repo_id, "fork/arsip/privat")
            return None, {"full_name": full_name, "reason": "fork/arsip/privat"}
    except Exception as err:
        _record_exclusion(db_path, repo_id, f"gagal api: {err}")
        return None, {"full_name": full_name, "reason": f"gagal api: {err}"}

    clone_dest = _clone_or_fetch_repo(full_name, runner)
    try:
        tag, first_dt, rel_dt, dur, n_contrib, kloc = _extract_git_metrics(clone_dest, manual_tag, runner)
        if not tag:
            _record_exclusion(db_path, repo_id, "tidak ada rilis stabil")
            return None, {"full_name": full_name, "reason": "tidak ada rilis stabil"}

        if dur <= 0:
            _record_exclusion(db_path, repo_id, "durasi tidak valid (<= 0)")
            return None, {"full_name": full_name, "reason": "durasi tidak valid"}

        q_iss = f"repo:{full_name} is:issue created:<={rel_dt[:10]}"
        q_prs = f"repo:{full_name} is:pr created:<={rel_dt[:10]}"
        n_work = client.search_count(q_iss) + client.search_count(q_prs)

        if not (1.0 <= dur <= 60.0 and 2 <= n_contrib <= 300 and 1.0 <= kloc <= 500.0):
            _record_exclusion(db_path, repo_id, "di luar kriteria numerik")
            return None, {"full_name": full_name, "reason": "di luar kriteria numerik"}

        with connection.transaction(db_path) as conn:
            training_rows_repo.add_training_row(
                conn, repo_id, tag, rel_dt, first_dt, dur, n_contrib, n_work, kloc, 1, None
            )
        return {
            "full_name": full_name, "release_tag": tag, "duration_months": dur,
            "n_contributors": n_contrib, "n_work_items": n_work, "kloc": kloc,
        }, None
    finally:
        if delete_clones and clone_dest.exists():
            shutil.rmtree(clone_dest, ignore_errors=True)


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
        meta = json.load(f)
    repos_config = meta.get("repos", [])
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

    results_included, results_excluded = [], []
    for entry in repos_config:
        try:
            inc, exc = _process_single_repo(entry, monitor_repos, client, runner, db_path, delete_clones, refresh)
            if inc:
                results_included.append(inc)
            if exc:
                results_excluded.append(exc)
        except RateLimitError as rl:
            results_excluded.append({"full_name": entry.get("full_name"), "reason": f"rate limit: {rl}"})
            break
        except Exception as e:
            results_excluded.append({"full_name": entry.get("full_name"), "reason": f"error: {e}"})

    _export_training_csvs(results_included, results_excluded)
    return {
        "status": "success",
        "n_included": len(results_included),
        "n_excluded": len(results_excluded),
        "warning_insufficient": len(results_included) < config.MIN_TRAINING_ROWS,
    }


def _record_exclusion(db_path: str | Path | None, repo_id: int, reason: str) -> None:
    """Mencatat baris pengecualian repositori latih ke tabel training_rows."""
    with connection.transaction(db_path) as conn:
        training_rows_repo.add_training_row(
            conn=conn, repo_id=repo_id, release_tag=None, release_date=None,
            first_commit_date=None, duration_months=None, n_contributors=None,
            n_work_items=None, kloc=None, included=0, exclusion_reason=reason,
        )


def _export_training_csvs(included: list[dict[str, Any]], excluded: list[dict[str, Any]]) -> None:
    """Mengekspor berkas data latih training_dataset.csv dan training_exclusions.csv."""
    if included:
        pd.DataFrame(included).to_csv(DATASET_CSV_PATH, index=False)
    if excluded:
        pd.DataFrame(excluded).to_csv(EXCLUSIONS_CSV_PATH, index=False)


def train_models_service(db_path: str | Path | None = None) -> dict[str, Any]:
    """Melatih Model A (data GitHub) dan Model B (NASA93) jika data tersedia."""
    summary: dict[str, Any] = {"model_a": None, "model_b": None, "messages": []}

    with connection.transaction(db_path) as conn:
        rows = training_rows_repo.list_training_rows(conn, included_only=True)

    if not rows:
        summary["messages"].append("Data latih Model A belum tersedia di database.")
    else:
        df_a = pd.DataFrame(rows)
        _, metrics_a = train_model_a(df_a)
        summary["model_a"] = metrics_a
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
