"""Pengujian analisis sentimen domain teknis, prapemrosesan, klasifikator, dan validasi."""
from pathlib import Path
import pandas as pd
import pytest

from app.sentiment.analyzer import VaderSentimentAnalyzer
from app.sentiment.classifier import (
    SklearnSentimentClassifier,
    get_active_sentiment_analyzer,
    train_and_evaluate_classifier,
)
from app.sentiment.preprocess import clean_text
from app.sentiment.validator import validate_sentiment
from app.services.sentiment_service import calculate_sentiment_index


def test_preprocess_cleaning() -> None:
    """Menguji pembersihan markdown, kode sebaris, blok kode, URL, mention, dan kutipan."""
    # 1. Hapus blok kode dan kode sebaris
    raw1 = "Here is the error:\n```python\ndef crash():\n    raise Exception()\n```\nCheck `var x = 1` please."
    cleaned1 = clean_text(raw1)
    assert "def crash" not in cleaned1
    assert "var x" not in cleaned1
    assert "Here is the error: Check please." == cleaned1

    # 2. Hapus URL dan kutipan balasan
    raw2 = "> this is quoted text\nSee https://github.com/issue/12 for details. [Documentation](https://doc.org)"
    cleaned2 = clean_text(raw2)
    assert "quoted text" not in cleaned2
    assert "https://" not in cleaned2
    assert "Documentation" in cleaned2

    # 3. Hapus mention dan HTML tag
    raw3 = "Thanks @developer for <span class='badge'>fixing</span> this ![logo](logo.png)!"
    cleaned3 = clean_text(raw3)
    assert "@developer" not in cleaned3
    assert "<span" not in cleaned3
    assert "fixing this !" in cleaned3

    # 4. Teks kosong setelah dibersihkan
    assert clean_text("```code only```") == ""
    assert clean_text(None) == ""
    assert clean_text("   \n\t  ") == ""


def test_vader_technical_neutral_words() -> None:
    """Memastikan kata-kata teknis netral (bug, error, exception) tidak otomatis bernilai negatif."""
    analyzer = VaderSentimentAnalyzer()

    # Kalimat teknis informatif tanpa sentimen emosional
    score_bug, label_bug = analyzer.analyze("there is a bug in the parser")
    assert label_bug == "netral"
    assert -0.05 < score_bug < 0.05

    score_err, label_err = analyzer.analyze("syntax error occurred")
    assert label_err == "netral"

    # Kalimat positif yang jelas
    score_pos, label_pos = analyzer.analyze("This library is awesome and works beautifully!")
    assert label_pos == "positif"
    assert score_pos >= 0.05

    # Kalimat negatif yang jelas
    score_neg, label_neg = analyzer.analyze("This is awful, completely broken and terrible experience.")
    assert label_neg == "negatif"
    assert score_neg <= -0.05

    # Teks kosong menghasilkan skor 0 dan label netral
    score_empty, label_empty = analyzer.analyze("```\ncode block\n```")
    assert score_empty == 0.0
    assert label_empty == "netral"


def test_classifier_minimum_labels_and_selection(tmp_path: Path, monkeypatch) -> None:
    """Memastikan klasifikator hanya dilatih jika label >= 150 dan aturan ambang F1 bekerja."""
    # Skenario 1: Label kurang dari 150
    df_small = pd.DataFrame({
        "text": ["great feature", "bad error", "normal update"],
        "label": ["positif", "negatif", "netral"],
    })
    res_small = train_and_evaluate_classifier(df_small, min_samples=150)
    assert res_small["trained"] is False
    assert "kurang dari batas minimal" in res_small["reason"]

    # Skenario 2: Data mencukupi (misal 150 sampel sintetis)
    texts = (
        ["amazing good great fantastic excellent" for _ in range(50)] +
        ["neutral informative status documentation update" for _ in range(50)] +
        ["horrible terrible awful worst disaster" for _ in range(50)]
    )
    labels = ["positif"] * 50 + ["netral"] * 50 + ["negatif"] * 50
    df_large = pd.DataFrame({"text": texts, "label": labels})

    custom_method_path = tmp_path / "sentiment_method.json"
    custom_model_path = tmp_path / "sentiment_classifier.joblib"
    monkeypatch.setattr("app.sentiment.classifier.SENTIMENT_METHOD_PATH", custom_method_path)
    monkeypatch.setattr("app.sentiment.classifier.SENTIMENT_MODEL_PATH", custom_model_path)

    res_large = train_and_evaluate_classifier(df_large, min_samples=150)
    assert res_large["trained"] is True
    info = res_large["method_info"]
    assert info["method"] in ("classifier", "vader")
    assert "delta_f1" in info
    assert custom_method_path.exists()


def test_validate_sentiment_missing_and_existing(tmp_path: Path) -> None:
    """Menguji penanganan validator saat berkas label tidak ada dan saat tersedia."""
    # 1. Berkas label belum ada
    missing_csv = tmp_path / "non_existent.csv"
    res_missing = validate_sentiment(labels_path=missing_csv)
    assert res_missing["validated"] is False
    assert "belum tersedia" in res_missing["message"]

    # 2. Berkas label tersedia
    labels_csv = tmp_path / "sentiment_labels.csv"
    out_json = tmp_path / "validation.json"
    df = pd.DataFrame({
        "comment_id": [1, 2, 3],
        "text": [
            "This is fantastic and works great",
            "This is broken and horrible",
            "Updated documentation for release",
        ],
        "label": ["positif", "negatif", "netral"],
    })
    df.to_csv(labels_csv, index=False)

    res_valid = validate_sentiment(labels_path=labels_csv, output_path=out_json)
    assert res_valid["validated"] is True
    assert res_valid["n_samples"] == 3
    assert "accuracy" in res_valid["vader"]
    assert "macro_f1" in res_valid["vader"]
    assert "confusion_matrix" in res_valid["vader"]
    assert out_json.exists()


def test_sentiment_index_calculation() -> None:
    """Memastikan rumus indeks sentimen (pos - neg) / total berada pada rentang -1.0 hingga +1.0."""
    assert calculate_sentiment_index(n_positive=10, n_negative=0, n_comments=10) == 1.0
    assert calculate_sentiment_index(n_positive=0, n_negative=10, n_comments=10) == -1.0
    assert calculate_sentiment_index(n_positive=5, n_negative=5, n_comments=10) == 0.0
    assert calculate_sentiment_index(n_positive=7, n_negative=2, n_comments=10) == 0.5
    assert calculate_sentiment_index(n_positive=0, n_negative=0, n_comments=0) == 0.0
