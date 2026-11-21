"""Layanan bisnis analisis sentimen, validasi manual, dan ekspor sampel komentar."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import pandas as pd

from app import config
from app.db import comments_repo, connection
from app.sentiment.classifier import get_active_sentiment_analyzer
from app.sentiment.validator import validate_sentiment

SAMPLE_EXPORT_PATH: Path = config.BASE_DIR / "data" / "labels" / "sample_to_label.csv"


def calculate_sentiment_index(n_positive: int, n_negative: int, n_comments: int) -> float:
    """Menghitung indeks sentimen agregat dari -1.0 hingga +1.0."""
    if n_comments <= 0:
        return 0.0
    val = (n_positive - n_negative) / float(n_comments)
    return round(max(-1.0, min(1.0, val)), 4)


def export_label_sample(
    n: int = 200,
    db_path: str | Path | None = None,
    output_path: Path | None = None,
) -> int:
    """Mengekspor sampel komentar ke CSV untuk pelabelan manual pemilik."""
    out_file = output_path or SAMPLE_EXPORT_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with connection.transaction(db_path) as conn:
        samples = comments_repo.get_comments_for_export(conn, limit=n)

    rows = []
    for s in samples:
        rows.append({
            "comment_id": s["comment_id"],
            "text": s["text"],
            "label": "",  # Dibiarkan kosong untuk diisi manual oleh pemilik
        })

    df = pd.DataFrame(rows)
    df.to_csv(out_file, index=False, encoding="utf-8")
    return len(rows)


def validate_sentiment_service(labels_path: Path | None = None) -> dict[str, Any]:
    """Menjalankan validasi akurasi dan macro-F1 terhadap label manual."""
    return validate_sentiment(labels_path=labels_path)


def rescore_comments_service(db_path: str | Path | None = None) -> dict[str, Any]:
    """Menghitung ulang label sentimen pada tabel comments (tidak mengubah daily_stats)."""
    analyzer = get_active_sentiment_analyzer()
    count_updated = 0

    with connection.transaction(db_path) as conn:
        sql = "SELECT id, body FROM comments"
        rows = conn.execute(sql).fetchall()
        for r in rows:
            cid = r["id"]
            body = r["body"]
            score, label = analyzer.analyze(body)
            comments_repo.update_comment_sentiment(conn, cid, score, label)
            count_updated += 1

    return {
        "status": "success",
        "comments_rescored": count_updated,
        "method": getattr(analyzer, "__class__", type(analyzer)).__name__,
    }
