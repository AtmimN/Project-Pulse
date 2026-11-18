# Label Sentimen Manual

Berkas `sentiment_labels.csv` (dibuat pemilik repositori) berisi sampel komentar yang dilabeli manual:

| Kolom | Isi |
|---|---|
| `comment_id` | id komentar GitHub (dari hasil `python -m app.cli export-label-sample`) |
| `text` | isi komentar (sudah dibersihkan seperlunya) |
| `label` | `positif`, `netral`, atau `negatif` (dilabeli manual) |

Disarankan minimal 150 baris (idealnya 200–300) dengan sebaran ketiga label. Jangan mengisi label dengan hasil model.
