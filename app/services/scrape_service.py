"""Layanan scraping incremental repositori pantau, sentimen, dan pembatasan data."""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app import config
from app.db import (
    comments_repo,
    connection,
    daily_stats_repo,
    issues_repo,
    job_runs_repo,
    keywords_repo,
    releases_repo,
    repos_repo,
    scrape_state_repo,
)
from app.scraper.github_client import AuthError, GitHubClient, RateLimitError
from app.sentiment.classifier import get_active_sentiment_analyzer
from app.sentiment.preprocess import clean_text

try:
    APP_TZ = ZoneInfo(config.TIMEZONE)
except Exception:
    APP_TZ = timezone.utc


def to_stat_date(iso_str: str) -> str:
    """Mengonversi timestamp ISO 8601 ke format YYYY-MM-DD dalam zona waktu aplikasi."""
    cleaned = iso_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(APP_TZ).strftime("%Y-%m-%d")


def is_bot_user(user: dict[str, Any] | None) -> bool:
    """Memeriksa apakah akun pengguna GitHub adalah bot."""
    if not user:
        return False
    if user.get("type") == "Bot":
        return True
    login = str(user.get("login", "")).lower()
    if login.endswith("[bot]"):
        return True
    return login in [x.lower() for x in config.IGNORED_LOGINS]


def _extract_issue_number(c: dict[str, Any]) -> int:
    """Mengekstrak nomor issue atau PR dari payload komentar."""
    if "issue_number" in c and c["issue_number"]:
        return int(c["issue_number"])
    url = c.get("issue_url") or c.get("pull_request_url") or ""
    m = re.search(r"/(?:issues|pulls)/(\d+)", url)
    return int(m.group(1)) if m else 0


def _resolve_labels(
    conn: sqlite3.Connection,
    repo_id: int,
    full_name: str,
    number: int,
    client: GitHubClient,
    counter: list[int],
) -> list[str]:
    """Mengambil label dari tabel issues atau memanggil GitHub API (maks 50 per siklus)."""
    if number <= 0:
        return []
    issue = issues_repo.get_issue(conn, repo_id, number)
    if issue:
        return issue.get("labels", [])

    if counter[0] < 50:
        try:
            raw = client.get_issue(full_name, number)
            labels = [lbl.get("name") for lbl in raw.get("labels", []) if lbl.get("name")]
            is_pr = 1 if "pull_request" in raw else 0
            issues_repo.save_issue(
                conn, repo_id, number, is_pr, labels,
                raw.get("state", "open"), raw.get("created_at", ""), raw.get("updated_at", "")
            )
            counter[0] += 1
            return labels
        except Exception:
            pass
    return []


def _sync_issues(
    conn: sqlite3.Connection,
    repo_id: int,
    full_name: str,
    client: GitHubClient,
    since: str,
) -> None:
    """Menyinkronkan daftar issue dan PR yang diperbarui sejak watermark."""
    raw_issues = client.list_issues(full_name, since=since)
    for it in raw_issues:
        num = it.get("number", 0)
        if not num:
            continue
        is_pr = 1 if "pull_request" in it else 0
        labels = [lbl.get("name") for lbl in it.get("labels", []) if lbl.get("name")]
        issues_repo.save_issue(
            conn, repo_id, num, is_pr, labels,
            it.get("state", "open"), it.get("created_at", ""), it.get("updated_at", "")
        )
    scrape_state_repo.upsert_scrape_state(
        conn, repo_id, "issues",
        last_updated_at=datetime.now(timezone.utc).isoformat(),
        last_success_at=datetime.now(timezone.utc).isoformat(),
    )


def _process_comment_entry(
    conn: sqlite3.Connection,
    repo_id: int,
    full_name: str,
    kind: str,
    c: dict[str, Any],
    floor: str | None,
    analyzer: Any,
    keywords: list[str],
    client: GitHubClient,
    counter: list[int],
) -> bool:
    """Memvalidasi, menganalisis, dan menyimpan satu komentar GitHub."""
    created_at = c.get("created_at", "")
    if not created_at or (floor and created_at <= floor):
        return False
    if is_bot_user(c.get("user")):
        return False

    cid = c.get("id")
    if not cid:
        return False

    num = _extract_issue_number(c)
    labels = _resolve_labels(conn, repo_id, full_name, num, client, counter)
    body = c.get("body", "")
    cleaned = clean_text(body)
    score, label = analyzer.analyze(cleaned)
    is_pr = 1 if kind == "review_comment" else 0

    inserted = comments_repo.save_comment(
        conn=conn, repo_id=repo_id, kind=kind, comment_id=cid, issue_number=num,
        is_pr=is_pr, labels=labels, body=body, created_at=created_at,
        sentiment_score=score, sentiment_label=label,
    )
    if inserted:
        stat_date = to_stat_date(created_at)
        n_pos = 1 if label == "positif" else 0
        n_neu = 1 if label == "netral" else 0
        n_neg = 1 if label == "negatif" else 0
        daily_stats_repo.upsert_daily_stats(conn, repo_id, stat_date, 1, n_pos, n_neu, n_neg)
        keywords_repo.record_keyword_hits(conn, repo_id, stat_date, cleaned, keywords)
    return inserted


def _sync_comments_stream(
    conn: sqlite3.Connection,
    repo_id: int,
    full_name: str,
    kind: str,
    client: GitHubClient,
    analyzer: Any,
    keywords: list[str],
    backfill_iso: str,
    counter: list[int],
) -> int:
    """Menyinkronkan satu aliran komentar (issue_comment atau review_comment)."""
    st = scrape_state_repo.get_scrape_state(conn, repo_id, kind)
    since = (st.get("last_updated_at") if st else None) or backfill_iso
    floor = st.get("floor_created_at") if st else None

    raw = client.list_issue_comments(full_name, since=since) if kind == "issue_comment" else client.list_review_comments(full_name, since=since)
    new_count = 0
    for c in raw:
        if _process_comment_entry(conn, repo_id, full_name, kind, c, floor, analyzer, keywords, client, counter):
            new_count += 1

    scrape_state_repo.upsert_scrape_state(
        conn, repo_id, kind,
        last_updated_at=datetime.now(timezone.utc).isoformat(),
        last_success_at=datetime.now(timezone.utc).isoformat(),
    )
    return new_count


def _sync_releases(conn: sqlite3.Connection, repo_id: int, full_name: str, client: GitHubClient) -> int:
    """Menyinkronkan rilis publik non-draft untuk repositori."""
    raw = client.list_releases(full_name)
    new_count = 0
    for r in raw:
        if r.get("draft") is True:
            continue
        rid = r.get("id")
        tag = r.get("tag_name") or r.get("tag") or ""
        pub = r.get("published_at") or r.get("created_at") or ""
        if not rid or not tag or not pub:
            continue
        prerel = 1 if r.get("prerelease") else 0
        rowid = releases_repo.add_release(conn, repo_id, rid, tag, pub, r.get("name"), prerel)
        if rowid > 0:
            new_count += 1

    scrape_state_repo.upsert_scrape_state(
        conn, repo_id, "releases",
        last_updated_at=datetime.now(timezone.utc).isoformat(),
        last_success_at=datetime.now(timezone.utc).isoformat(),
    )
    return new_count


def scrape_single_repo(
    repo: dict[str, Any],
    client: GitHubClient,
    analyzer: Any,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Menjalankan scraping incremental satu repositori dalam satu transaksi."""
    repo_id = repo["id"]
    full_name = repo["full_name"]
    now_utc = datetime.now(timezone.utc)
    backfill_iso = (now_utc - timedelta(days=config.BACKFILL_DAYS)).isoformat()
    issue_fetch_counter = [0]

    with connection.transaction(db_path) as conn:
        kw_rows = keywords_repo.list_keywords(conn)
        keywords = [k["word"] for k in kw_rows]

        # 1. Aliran issues
        st_iss = scrape_state_repo.get_scrape_state(conn, repo_id, "issues")
        since_iss = (st_iss.get("last_updated_at") if st_iss else None) or backfill_iso
        _sync_issues(conn, repo_id, full_name, client, since_iss)

        # 2. Aliran komentar
        new_ic = _sync_comments_stream(conn, repo_id, full_name, "issue_comment", client, analyzer, keywords, backfill_iso, issue_fetch_counter)
        new_rc = _sync_comments_stream(conn, repo_id, full_name, "review_comment", client, analyzer, keywords, backfill_iso, issue_fetch_counter)
        total_comments = new_ic + new_rc

        # 3. Aliran rilis
        new_rels = _sync_releases(conn, repo_id, full_name, client)

        # 4. Pembatasan data (pruning)
        new_floor = comments_repo.prune_comments(conn, repo_id, max_comments=config.MAX_COMMENTS_PER_REPO)
        if new_floor:
            scrape_state_repo.upsert_scrape_state(conn, repo_id, "issue_comments", floor_created_at=new_floor)
            scrape_state_repo.upsert_scrape_state(conn, repo_id, "review_comments", floor_created_at=new_floor)

    return {
        "full_name": full_name,
        "status": "berhasil",
        "new_comments": total_comments,
        "new_releases": new_rels,
        "error": None,
    }


def scrape_all_monitor_repos(
    github_client: GitHubClient | None = None,
    db_path: str | Path | None = None,
    trigger: str = "manual",
) -> dict[str, Any]:
    """Menjalankan siklus scraping untuk seluruh repositori pantau aktif."""
    client = github_client or GitHubClient()
    analyzer = get_active_sentiment_analyzer()

    with connection.transaction(db_path) as conn:
        repos_repo.ensure_monitor_repos_loaded(conn)
        target_repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
        job_id = job_runs_repo.start_job(conn, "scrape", trigger)

    results: list[dict[str, Any]] = []
    tot_comments, tot_releases = 0, 0
    hit_rate_limit = False

    for i, r in enumerate(target_repos):
        if hit_rate_limit:
            results.append({"full_name": r["full_name"], "status": "dilewati", "error": "rate limit"})
            continue
        try:
            res = scrape_single_repo(r, client, analyzer, db_path)
            tot_comments += res["new_comments"]
            tot_releases += res["new_releases"]
            results.append(res)
        except RateLimitError as rl:
            hit_rate_limit = True
            results.append({"full_name": r["full_name"], "status": "dilewati", "error": str(rl)})
        except AuthError as ae:
            results.append({"full_name": r["full_name"], "status": "gagal", "error": str(ae)})
            with connection.transaction(db_path) as conn:
                job_runs_repo.finish_job(conn, job_id, "gagal", tot_comments, tot_releases, {"results": results, "error": str(ae)})
            raise
        except Exception as ex:
            results.append({"full_name": r["full_name"], "status": "gagal", "error": str(ex)})

    final_status = "gagal" if all(r["status"] == "gagal" for r in results) else ("sebagian" if any(r["status"] != "berhasil" for r in results) else "berhasil")
    with connection.transaction(db_path) as conn:
        job_runs_repo.finish_job(conn, job_id, final_status, tot_comments, tot_releases, {"results": results})

    return {
        "job_id": job_id,
        "status": final_status,
        "new_comments": tot_comments,
        "new_releases": tot_releases,
        "results": results,
    }
