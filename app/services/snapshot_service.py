"""Layanan pengambilan snapshot metrik git untuk repositori pantau."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from app import config
from app.db import connection, repos_repo, snapshots_repo
from app.scraper.github_client import GitHubClient
from app.scraper.repo_metrics import (
    GitRunner,
    calculate_duration_months,
    contributors_until,
    find_first_stable_release_tag,
    first_commit_date,
    kloc_at,
    release_date,
)


def snapshot_single_repo(
    repo_id: int,
    full_name: str,
    github_client: GitHubClient | None = None,
    git_runner: GitRunner | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mengambil snapshot metrik saat ini (now) dan rilis stabil pertama (first_stable)."""
    client = github_client or GitHubClient()
    runner = git_runner or GitRunner()

    clone_dest = Path(config.CLONE_DIR) / f"{full_name.replace('/', '__')}.git"
    clone_dest.parent.mkdir(parents=True, exist_ok=True)

    if not clone_dest.exists():
        runner.run(["clone", "--bare", "--filter=blob:none", f"https://github.com/{full_name}.git", str(clone_dest)])
    else:
        runner.run(["fetch", "--tags", "--prune"], cwd=clone_dest)

    first_dt = first_commit_date(clone_dest, runner)

    # 1. Snapshot as_of='now'
    contrib_now = contributors_until(clone_dest, "HEAD", runner)
    kloc_now = kloc_at(clone_dest, "HEAD", runner)
    q_issues = f"repo:{full_name} is:issue"
    q_prs = f"repo:{full_name} is:pr"
    work_now = client.search_count(q_issues) + client.search_count(q_prs)

    with connection.transaction(db_path) as conn:
        snapshots_repo.save_snapshot(
            conn=conn,
            repo_id=repo_id,
            as_of="now",
            n_contributors=contrib_now,
            n_work_items=work_now,
            kloc=kloc_now,
            first_commit_date=first_dt,
        )

    # 2. Snapshot as_of='first_stable' (jika ada)
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
    stable_tag = find_first_stable_release_tag(tag_entries)

    dur_stable: float | None = None
    if stable_tag:
        rel_dt = release_date(clone_dest, stable_tag, runner)
        dur_stable = calculate_duration_months(first_dt, rel_dt)
        contrib_stable = contributors_until(clone_dest, stable_tag, runner)
        kloc_stable = kloc_at(clone_dest, stable_tag, runner)
        q_iss_stable = f"repo:{full_name} is:issue created:<={rel_dt[:10]}"
        q_pr_stable = f"repo:{full_name} is:pr created:<={rel_dt[:10]}"
        work_stable = client.search_count(q_iss_stable) + client.search_count(q_pr_stable)

        with connection.transaction(db_path) as conn:
            snapshots_repo.save_snapshot(
                conn=conn,
                repo_id=repo_id,
                as_of="first_stable",
                n_contributors=contrib_stable,
                n_work_items=work_stable,
                kloc=kloc_stable,
                first_commit_date=first_dt,
                release_tag=stable_tag,
                release_date=rel_dt,
                duration_months=dur_stable,
            )

    return {
        "repo": full_name,
        "kloc_now": kloc_now,
        "contributors_now": contrib_now,
        "work_items_now": work_now,
        "stable_tag": stable_tag,
        "duration_first_stable": dur_stable,
    }


def snapshot_all_monitor_repos(
    github_client: GitHubClient | None = None,
    git_runner: GitRunner | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Memperbarui snapshot untuk seluruh repositori pantau yang aktif."""
    with connection.transaction(db_path) as conn:
        active_repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)

    results = []
    for r in active_repos:
        try:
            res = snapshot_single_repo(
                repo_id=r["id"],
                full_name=r["full_name"],
                github_client=github_client,
                git_runner=git_runner,
                db_path=db_path,
            )
            results.append({"status": "success", "data": res})
        except Exception as err:
            results.append({"status": "error", "repo": r["full_name"], "error": str(err)})
    return results
