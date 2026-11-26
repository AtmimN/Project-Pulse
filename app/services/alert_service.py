"""Layanan bisnis evaluasi alert, uji ulang (backtest), dan pengiriman notifikasi/digest."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import pandas as pd
from zoneinfo import ZoneInfo

from app import config
from app.alerts.engine import evaluate_all_rules
from app.db import alerts_repo, connection, repos_repo

BACKTEST_CSV_PATH: Path = config.BASE_DIR / "models" / "alert_backtest.csv"
try:
    APP_TZ = ZoneInfo(config.TIMEZONE)
except Exception:
    APP_TZ = timezone.utc


def _get_active_tiers(conn: Any) -> dict[str, Any]:
    """Mengambil konfigurasi ambang batas alert kustom jika tersedia di database."""
    raw = alerts_repo.get_alert_setting(conn, "alert_tiers")
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _save_and_queue_alert(
    conn: Any, rid: int, r_name: str, c: dict[str, Any], target_date: str
) -> dict[str, Any] | None:
    """Menyimpan satu alert ke basis data dan memasukkannya ke antrean pengiriman pelanggan."""
    aid = alerts_repo.add_alert(
        conn, rid, c["alert_type"], c["strength"], c["detail"], target_date, c["dedupe_key"]
    )
    if not aid:
        return None
    c["id"] = aid
    c["repo_name"] = r_name
    for s in alerts_repo.get_subscribers_for_alert(conn, rid, c["strength"]):
        alerts_repo.queue_alert_delivery(conn, aid, s["chat_id"])
    return c


def _eval_single_monitor_repo_alerts(
    conn: Any, r: dict[str, Any], target_date: str, custom_tiers: dict[str, Any]
) -> list[dict[str, Any]]:
    """Mengevaluasi seluruh aturan alert untuk satu repositori pantau."""
    rid = r["id"]
    d_stats = [dict(w) for w in conn.execute("SELECT * FROM daily_stats WHERE repo_id = ?", (rid,)).fetchall()]
    kw_daily = [dict(w) for w in conn.execute("SELECT * FROM keyword_daily WHERE repo_id = ?", (rid,)).fetchall()]
    rels = [dict(w) for w in conn.execute("SELECT * FROM releases WHERE repo_id = ?", (rid,)).fetchall()]

    saved: list[dict[str, Any]] = []
    for c in evaluate_all_rules(rid, d_stats, kw_daily, rels, target_date, custom_tiers):
        res = _save_and_queue_alert(conn, rid, r["full_name"], c, target_date)
        if res:
            saved.append(res)
    return saved


def evaluate_and_save_alerts(
    alert_date: str | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Mengevaluasi aturan alert untuk repositori pantau dan mencatatnya ke basis data."""
    target_date = alert_date or datetime.now(APP_TZ).strftime("%Y-%m-%d")
    saved_alerts: list[dict[str, Any]] = []

    with connection.transaction(db_path) as conn:
        repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
        custom_tiers = _get_active_tiers(conn)
        for r in repos:
            saved_alerts.extend(_eval_single_monitor_repo_alerts(conn, r, target_date, custom_tiers))

    return saved_alerts


def _backtest_single_repo(
    r: dict[str, Any], today: Any, days: int, custom_tiers: dict[str, Any], conn: Any
) -> list[dict[str, Any]]:
    """Menjalankan evaluasi mundur untuk satu repositori."""
    rid = r["id"]
    d_stats = [dict(w) for w in conn.execute("SELECT * FROM daily_stats WHERE repo_id = ?", (rid,)).fetchall()]
    kw_daily = [dict(w) for w in conn.execute("SELECT * FROM keyword_daily WHERE repo_id = ?", (rid,)).fetchall()]
    rels = [dict(w) for w in conn.execute("SELECT * FROM releases WHERE repo_id = ?", (rid,)).fetchall()]

    candidates = []
    for d_offset in range(days, -1, -1):
        cur_date_str = (today - timedelta(days=d_offset)).strftime("%Y-%m-%d")
        for item in evaluate_all_rules(rid, d_stats, kw_daily, rels, cur_date_str, custom_tiers):
            item["repo_name"] = r["full_name"]
            candidates.append(item)
    return candidates


def backtest_alerts(
    days: int = 60,
    repo_name: str | None = None,
    db_path: str | Path | None = None,
    output_csv: Path | None = None,
) -> dict[str, Any]:
    """Menjalankan simulasi aturan alert mundur tanpa menulis ke tabel alerts atau notifier."""
    out_file = output_csv or BACKTEST_CSV_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(APP_TZ).date()

    with connection.transaction(db_path) as conn:
        repos = repos_repo.list_repos(conn, kind="monitor", active_only=True)
        if repo_name:
            repos = [r for r in repos if r["full_name"].lower() == repo_name.strip().lower()]
        custom_tiers = _get_active_tiers(conn)

        all_candidates: list[dict[str, Any]] = []
        for r in repos:
            all_candidates.extend(_backtest_single_repo(r, today, days, custom_tiers, conn))

    rows = [{
        "date": c["alert_date"], "repo": c["repo_name"], "alert_type": c["alert_type"],
        "strength": c["strength"], "detail": json.dumps(c["detail"]),
    } for c in all_candidates]
    pd.DataFrame(rows).to_csv(out_file, index=False, encoding="utf-8")

    summary_counts: dict[str, dict[str, int]] = {}
    for c in all_candidates:
        atype, st = c["alert_type"], c["strength"]
        summary_counts.setdefault(atype, {"lemah": 0, "sedang": 0, "kuat": 0})
        summary_counts[atype][st] = summary_counts[atype].get(st, 0) + 1

    return {"total_alerts": len(all_candidates), "counts": summary_counts, "csv_path": str(out_file)}


def deliver_pending_alerts(notifier: Any = None, db_path: str | Path | None = None) -> dict[str, int]:
    """Mengirim alert yang ada di antrean pengiriman ke pelanggan melalui notifier."""
    delivered, failed = 0, 0
    with connection.transaction(db_path) as conn:
        pending = alerts_repo.list_pending_deliveries(conn, max_attempts=3)
        for item in pending:
            aid, cid = item["alert_id"], item["chat_id"]
            attempts = item.get("attempts", 0) + 1
            if not notifier or not hasattr(notifier, "send_message"):
                continue

            msg = f"🔔 [{item['strength'].upper()}] {item['repo_name']}: {item['alert_type']} ({item['alert_date']})"
            try:
                success = notifier.send_message(cid, msg)
                status = "terkirim" if success else "gagal"
                sent_at = datetime.now().isoformat() if success else None
                alerts_repo.update_delivery_status(conn, aid, cid, status, attempts, sent_at)
                delivered += 1 if success else 0
                failed += 0 if success else 1
            except Exception:
                alerts_repo.update_delivery_status(conn, aid, cid, "gagal", attempts, None)
                failed += 1

    return {"delivered": delivered, "failed": failed}


def _format_digest_text(conn: sqlite3.Connection, chat_id: Any, target_date: str) -> str:
    """Menyusun teks ringkasan digest harian untuk seorang pelanggan."""
    q_watch = "SELECT r.id, r.full_name FROM watchlist w JOIN repos r ON w.repo_id = r.id WHERE w.chat_id = ?"
    rows = conn.execute(q_watch, (str(chat_id),)).fetchall()
    if not rows:
        return f"📋 [Digest Harian {target_date}]\nAnda belum memantau repositori apa pun."

    ref_dt = datetime.fromisoformat(target_date)
    d7_start = (ref_dt - timedelta(days=6)).strftime("%Y-%m-%d")
    lines = [f"📋 [Digest Harian {target_date}]"]
    has_new = False
    for r in rows:
        rid, name = r["id"], r["full_name"]
        st = conn.execute("SELECT n_comments, n_positive, n_negative FROM daily_stats WHERE repo_id = ? AND stat_date = ?", (rid, target_date)).fetchone()
        n_c = st["n_comments"] if st else 0
        s_idx = round((st["n_positive"] - st["n_negative"]) / float(n_c), 2) if n_c > 0 else 0.0

        q_7 = "SELECT SUM(n_comments) as tot, SUM(n_positive) as pos, SUM(n_negative) as neg FROM daily_stats WHERE repo_id = ? AND stat_date BETWEEN ? AND ?"
        s_7 = conn.execute(q_7, (rid, d7_start, target_date)).fetchone()
        idx_7 = round((s_7["pos"] - s_7["neg"]) / float(s_7["tot"]), 2) if (s_7 and s_7["tot"]) else 0.0

        if n_c > 0:
            has_new = True
            lines.append(f"• {name}: {n_c} komentar baru, sentimen {s_idx} (rata-rata 7h: {idx_7})")
        else:
            lines.append(f"• {name}: tidak ada komentar baru.")
    if not has_new:
        lines.append("Catatan: Tidak ada komentar baru di seluruh repositori pantau.")
    return "\n".join(lines)


def _send_single_digest(conn: Any, cid: int, target_date: str, notifier: Any) -> bool:
    """Mengirim ringkasan digest ke satu pelanggan Telegram."""
    if alerts_repo.is_digest_sent(conn, cid, target_date):
        return False
    msg = _format_digest_text(conn, cid, target_date)
    if not notifier or not hasattr(notifier, "send_message"):
        alerts_repo.record_digest(conn, cid, target_date)
        return True
    try:
        if notifier.send_message(cid, msg):
            alerts_repo.record_digest(conn, cid, target_date)
            return True
    except Exception as err:
        import logging
        logging.getLogger(__name__).warning("Gagal mengirim digest ke %s: %s", cid, err)
    return False


def send_daily_digest(digest_date: str | None = None, notifier: Any = None, db_path: str | Path | None = None) -> int:
    """Mengirim ringkasan digest harian kepada seluruh pelanggan aktif."""
    target_date = digest_date or datetime.now(APP_TZ).strftime("%Y-%m-%d")
    sent_count = 0
    with connection.transaction(db_path) as conn:
        subs = [dict(r) for r in conn.execute("SELECT chat_id FROM subscribers WHERE active = 1").fetchall()]
        for s in subs:
            if _send_single_digest(conn, s["chat_id"], target_date, notifier):
                sent_count += 1
    return sent_count
