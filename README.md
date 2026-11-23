# ProjectPulse

Asisten manajemen proyek berbasis web yang menilai **kesehatan sebuah proyek dari dua sisi**: **kecepatan** (estimasi durasi dari data repositori GitHub nyata, dibandingkan dengan model usaha dari NASA93) dan **suasana tim/pengguna** (sentimen komentar issue dan pull request). Dilengkapi **pemantauan otomatis**: penjadwal harian dan **bot Telegram** yang mengirim alert dan ringkasan.

Project akhir gabungan mata kuliah **Aplikasi Web** dan **Scripting Language**. Chatbot dikembangkan dari [PM-Bot](reference/PM-Bot/). Seluruh fitur bersumber dari satu data: repositori publik GitHub.

## Fitur Rencana
- Chatbot manajemen proyek (rule-based) yang membaca hasil dari database
- Estimasi proyek: Model A (durasi, dari repositori GitHub) dan Model B (usaha, dari NASA93) berdampingan, dengan penyesuaian level tim sebagai skenario
- Analisis sentimen komentar issue/PR dengan validasi sampel berlabel manual
- Scraping harian incremental repositori pantau; alert: sentimen turun, lonjakan negatif, rilis bermasalah, kata kunci
- Bot Telegram: watchlist, alert, digest harian, ringkasan, perbandingan
- Dashboard Chart.js dan halaman admin/pemantauan

## Teknologi
Python, Flask, SQLite (WAL), scikit-learn, GitHub REST API (`requests`) dan `git`, VADER, python-telegram-bot, APScheduler, Chart.js

## Temuan Evaluasi Durasi GitHub & Keputusan Model Estimasi (Milestone M6-rev)

Evaluasi model regresi linier durasi kalender dari repositori open source GitHub ("Model A") pada 30 repositori latih yang telah melewati aturan kualitas data menunjukkan **tidak adanya kemampuan prediksi yang memadai**:
- **Akurasi Validasi Silang (Repeated 5-Fold, 20x):** MAE model sebesar **7,16 bulan** (varian log1p) vs baseline tebakan median sebesar **10,89 bulan** (pada varian raw: MAE model 9,87 bulan vs baseline median 10,89 bulan; pada data latih yang lebih terfilter ketat di M6-rev: MAE 5,70 bulan vs tebak median 5,22 bulan dengan `improvement_pct` −9,14%).
- **R² Validasi Silang Out-of-Fold:** R² bernilai rendah atau negatif (−0,34 sampai 0,26), mengindikasikan varians durasi kalender tidak terjelaskan dengan baik oleh metrik kumulatif.
- **Korelasi Spearman Kontributor Kumulatif:** Korelasi positif yang muncul ($\rho \approx 0,12$ sampai $0,72$) semata-mata mencerminkan **usia proyek** (proyek yang lebih lama mengumpulkan lebih banyak kontributor kumulatif), bukan efek sebab-akibat bahwa menambah anggota mempercepat durasi.

### Keputusan:
1. **Halaman `/estimasi` hanya menggunakan Model B** (dataset industri NASA93 COCOMO81) untuk memprediksi usaha (person-bulan) dan durasi indikatif. Model A **tidak digunakan sebagai prediktor**.
2. **Data GitHub tetap difungsikan sebagai konteks empiris**: disajikan sebagai benchmark durasi rilis stabil pertama (median dan rentang kuartil Q1–Q3) serta analisis persentil beban kerja tim.
3. **Kartu Kesehatan Repositori (`/kesehatan`)**: menyatukan dimensi kecepatan proyek, beban per kontributor, dan suasana sentimen/alert. **Catatan:** hubungan statistik antara sentimen komunitas dan keterlambatan proyek belum diuji secara empiris dan menjadi agenda pekerjaan lanjutan.

## Status
Dalam pengembangan. Spesifikasi lengkap ada di [`instruction.md`](instruction.md) dan [`docs/instruction/`](docs/instruction/).

> README ini akan dilengkapi di akhir pengembangan (instalasi dan cara menjalankan).
