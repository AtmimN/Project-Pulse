"""Validasi metrik sentimen terhadap data sampel berlabel manual (modul murni)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from app import config
from app.sentiment.analyzer import VaderSentimentAnalyzer
from app.sentiment.classifier import (
    SENTIMENT_MODEL_PATH,
    SklearnSentimentClassifier,
)

LABELS_CSV_PATH: Path = config.BASE_DIR / "data" / "labels" / "sentiment_labels.csv"
VALIDATION_JSON_PATH: Path = config.BASE_DIR / "models" / "sentiment_validation.json"
LABELS_ORDER: list[str] = ["positif", "netral", "negatif"]


def _evaluate_model_performance(y_true: list[str], y_pred: list[str]) -> dict[str, Any]:
    """Menghitung akurasi, macro-F1, dan matriks konfusi."""
    acc = float(accuracy_score(y_true, y_pred))
    f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    cm = confusion_matrix(y_true, y_pred, labels=LABELS_ORDER).tolist()
    return {
        "accuracy": round(acc, 4),
        "macro_f1": round(f1, 4),
        "confusion_matrix": cm,
        "labels_order": LABELS_ORDER,
    }


def validate_sentiment(
    labels_path: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Mengevaluasi performa model sentimen terhadap berkas label manual."""
    target_path = labels_path or LABELS_CSV_PATH
    out_file = output_path or VALIDATION_JSON_PATH

    if not target_path.exists():
        return {
            "validated": False,
            "message": f"Berkas label manual {target_path} belum tersedia.",
        }

    df = pd.read_csv(target_path)
    if "text" not in df.columns or "label" not in df.columns or df.empty:
        return {
            "validated": False,
            "message": "Format berkas label tidak valid atau data kosong (membutuhkan kolom text dan label).",
        }

    # Saring baris yang memiliki label valid
    df_valid = df[df["label"].isin(LABELS_ORDER)].copy()
    if df_valid.empty:
        return {
            "validated": False,
            "message": "Tidak ada baris dengan label valid (positif/netral/negatif).",
        }

    y_true = df_valid["label"].astype(str).tolist()
    texts = df_valid["text"].fillna("").astype(str).tolist()

    # 1. Evaluasi VADER
    vader = VaderSentimentAnalyzer()
    y_pred_vader = [vader.analyze(t)[1] for t in texts]
    vader_metrics = _evaluate_model_performance(y_true, y_pred_vader)

    result: dict[str, Any] = {
        "validated": True,
        "n_samples": len(df_valid),
        "vader": vader_metrics,
        "classifier": None,
        "validated_at": datetime.now().isoformat(),
    }

    # 2. Evaluasi Classifier bila model ada
    if SENTIMENT_MODEL_PATH.exists():
        try:
            pipe = joblib.load(SENTIMENT_MODEL_PATH)
            clf = SklearnSentimentClassifier(pipe)
            y_pred_clf = [clf.analyze(t)[1] for t in texts]
            result["classifier"] = _evaluate_model_performance(y_true, y_pred_clf)
        except Exception:
            pass

    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result
