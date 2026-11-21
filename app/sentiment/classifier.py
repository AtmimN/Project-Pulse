"""Model klasifikasi sentimen alternatif berbasis TF-IDF dan Logistic Regression (modul murni)."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from app import config
from app.sentiment.analyzer import VaderSentimentAnalyzer
from app.sentiment.preprocess import clean_text

SENTIMENT_METHOD_PATH: Path = config.BASE_DIR / "models" / "sentiment_method.json"
SENTIMENT_MODEL_PATH: Path = config.BASE_DIR / "models" / "sentiment_classifier.joblib"


class SklearnSentimentClassifier:
    """Pembungkus model klasifikasi scikit-learn untuk inferensi sentimen."""

    def __init__(self, pipeline: Pipeline) -> None:
        self.pipeline = pipeline
        self.classes_ = list(pipeline.classes_)

    def analyze(self, text: str | None) -> tuple[float, str]:
        """Menganalisis teks menggunakan model terlatih dan mengembalikan (score, label)."""
        cleaned = clean_text(text)
        if not cleaned:
            return 0.0, "netral"

        pred_label = str(self.pipeline.predict([cleaned])[0])
        # Hitung skor kontinu dari probabilitas kelas P(positif) - P(negatif)
        try:
            probs = self.pipeline.predict_proba([cleaned])[0]
            prob_map = dict(zip(self.classes_, probs))
            score = float(prob_map.get("positif", 0.0) - prob_map.get("negatif", 0.0))
        except Exception:
            score = 1.0 if pred_label == "positif" else (-1.0 if pred_label == "negatif" else 0.0)

        return round(score, 4), pred_label


def train_and_evaluate_classifier(
    df_labels: pd.DataFrame,
    min_samples: int = 150,
) -> dict[str, Any]:
    """Melatih dan mengevaluasi klasifikator jika data memenuhi syarat minimal sampel."""
    if len(df_labels) < min_samples:
        return {
            "trained": False,
            "reason": f"Jumlah label ({len(df_labels)}) kurang dari batas minimal ({min_samples}).",
        }

    X = df_labels["text"].fillna("").astype(str).tolist()
    y = df_labels["label"].astype(str).tolist()

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=2, preprocessor=clean_text)),
        ("clf", LogisticRegression(class_weight="balanced", random_state=42, max_iter=1000)),
    ])
    pipe.fit(X_tr, y_tr)

    y_pred_clf = pipe.predict(X_te)
    f1_clf = float(f1_score(y_te, y_pred_clf, average="macro", zero_division=0))

    # Evaluasi VADER pada data uji yang sama
    vader = VaderSentimentAnalyzer()
    y_pred_vader = [vader.analyze(t)[1] for t in X_te]
    f1_vader = float(f1_score(y_te, y_pred_vader, average="macro", zero_division=0))

    delta_f1 = f1_clf - f1_vader
    use_classifier = delta_f1 >= config.CLASSIFIER_F1_THRESHOLD
    chosen_method = "classifier" if use_classifier else "vader"

    SENTIMENT_METHOD_PATH.parent.mkdir(parents=True, exist_ok=True)
    if use_classifier:
        joblib.dump(pipe, SENTIMENT_MODEL_PATH)

    method_info = {
        "method": chosen_method,
        "f1_classifier": round(f1_clf, 4),
        "f1_vader": round(f1_vader, 4),
        "delta_f1": round(delta_f1, 4),
        "threshold": config.CLASSIFIER_F1_THRESHOLD,
        "n_samples": len(df_labels),
        "evaluated_at": datetime.now().isoformat(),
    }
    with open(SENTIMENT_METHOD_PATH, "w", encoding="utf-8") as f:
        json.dump(method_info, f, indent=2)

    return {"trained": True, "method_info": method_info}


def get_active_sentiment_analyzer() -> Any:
    """Mengembalikan penganalisis sentimen aktif sesuai pilihan pada sentiment_method.json."""
    if SENTIMENT_METHOD_PATH.exists() and SENTIMENT_MODEL_PATH.exists():
        try:
            with open(SENTIMENT_METHOD_PATH, "r", encoding="utf-8") as f:
                info = json.load(f)
            if info.get("method") == "classifier":
                pipe = joblib.load(SENTIMENT_MODEL_PATH)
                return SklearnSentimentClassifier(pipe)
        except Exception:
            pass

    return VaderSentimentAnalyzer()
