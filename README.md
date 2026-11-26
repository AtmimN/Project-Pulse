# ProjectPulse

ProjectPulse adalah asisten manajemen proyek perangkat lunak berbasis web yang menilai **kesehatan proyek dari dua sisi**: **kecepatan** (estimasi usaha dan durasi dari data empiris industri NASA93 COCOMO 81 yang dikontekstualisasikan dengan benchmark repositori GitHub) serta **suasana tim dan pengguna** (analisis sentimen komentar issue dan pull request).

Proyek ini dilengkapi dengan **pemantauan otomatis harian** (penjadwal APScheduler) dan **Bot Telegram** interaktif untuk notifikasi alert, ringkasan berkala (*daily digest*), dan komparasi repositori.

Proyek ini merupakan proyek akhir gabungan mata kuliah **Aplikasi Web** dan **Scripting Language**, dengan chatbot rule-based yang diadaptasi dari [PM-Bot](reference/PM-Bot/).

---

## Daftar Isi
- [Tesis Proyek](#tesis-proyek)
- [Fitur Utama](#fitur-utama)
- [Teknologi](#teknologi)
- [Instalasi dan Konfigurasi](#instalasi-dan-konfigurasi)
- [Cara Menjalankan Tiga Proses Terpisah](#cara-menjalankan-tiga-proses-terpisah)
- [Panduan Antarmuka CLI](#panduan-antarmuka-cli)
- [Urutan Kerja Pemilik (Owner Workflow)](#urutan-kerja-pemilik-owner-workflow)
- [Temuan Evaluasi Durasi GitHub & Keputusan Model](#temuan-evaluasi-durasi-github--keputusan-model)
- [Keterbatasan Proyek](#keterbatasan-proyek)
- [Sumber Data](#sumber-data)

---

## Tesis Proyek

Keberhasilan proyek perangkat lunak tidak hanya ditentukan oleh metrik teknis atau kecepatan deliveri, melainkan perpaduan harmonis antara:
1. **Kecepatan (*Speed/Pace*):** Keselarasan antara estimasi beban kerja, durasi kalender historis, dan alokasi kontributor aktif.
2. **Suasana (*Mood/Pulse*):** Kondisi emosional dan dinamika komunikasi di lingkungan tim dan komunitas pengembang, yang tercermin dari sentimen diskusi issue dan code review pull request.

Dengan memantau kedua dimensi ini secara simultan melalui **Kartu Kesehatan Repositori**, manajer proyek dapat mengidentifikasi tanda-tanda kelelahan (*burnout*), friksi rilis, maupun risiko keterlambatan lebih dini.

---

## Fitur Utama

- **Chatbot Asisten Proyek (Rule-Based):**
  - Mesin pencocokan pola intent dengan kata kunci dan sinonim fleksibel.
  - Menjawab pertanyaan seputar manajemen proyek (Sprint, Risk, Team, Task, Quality, Scope).
  - Menyediakan ringkasan status repositori pantau langsung dari database.

- **Estimasi Usaha & Durasi Proyek (`/estimasi`):**
  - Menggunakan **Model B** (regresi linier berganda log-transformed berbasis dataset industri NASA93 COCOMO 81) untuk memprediksi usaha (*effort* dalam *person-months*) dan durasi kalender indikatif.
  - Penyesuaian skenario level tim (pemula, menengah, ahli) melalui pengali usaha COCOMO.
  - Dilengkapi analisis **Beban Kerja Tim** (KLOC per kontributor dan persentil) serta **Benchmark Durasi Rilis Pertama** dari repositori GitHub berkarakteristik serupa.

- **Analisis Sentimen Komentar Issue & PR:**
  - Analisis sentimen berbasis VADER dengan penyesuaian leksikon istilah teknis perangkat lunak (contoh: *bug*, *issue*, *error*, *fix*, *test* tidak otomatis dipandang negatif).
  - Validasi akurasi, Macro-F1, dan matriks konfusi terhadap sampel berlabel manual oleh pemilik.
  - Pilihan fallback klasifikator terlatih (MultinomialNB / Logistic Regression).

- **Scraping Inkremental & Pemantauan Data:**
  - Sinkronisasi otomatis komentar issue, pull request review, dan data rilis GitHub.
  - Mekanisme deduplikasi berbasis ID GitHub dan pemangkasan (*pruning*) data lama melebihi kapasitas per repositori tanpa merusak statistik historis (`daily_stats`).

- **Mesin Deteksi Alert (4 Jenis Alert):**
  - **Sentimen Turun (*Sentiment Drop*):** Penurunan indeks sentimen rata-rata 7 hari dibanding baseline 30 hari.
  - **Lonjakan Komentar Negatif (*Negative Spike*):** Peningkatan tajam persentase komentar negatif harian.
  - **Rilis Bermasalah (*Problematic Release*):** Kenaikan komentar negatif dalam rentang 3 hari pasca publikasi rilis dibanding periode pra-rilis.
  - **Kata Kunci Kritis (*Keyword Alert*):** Kemunculan kata kunci berisiko tinggi (misal: *crash*, *broken*, *security*, *revert*).
  - Dilengkapi fitur pengujian historis (*backtest*) untuk mengevaluasi efektivitas ambang batas.

- **Bot Telegram Interaktif:**
  - Perintah: `/start`, `/bantuan`, `/pantau`, `/berhenti`, `/watchlist`, `/ringkasan`, `/bandingkan`.
  - Notifikasi instan untuk alert baru pada repositori yang dipantau.
  - Pengiriman ringkasan harian (*daily digest*) terjadwal pada jam yang ditentukan.

- **Pulse Repositori (`/repositori`):**
  - Tampilan agregasi sentimen 30 hari (persentase positif, netral, negatif, serta indeks sentimen).
  - Grafik tren bulanan, kata-kata paling sering muncul (*word frequencies*), dan penelusuran komentar dengan filter sentimen dan paginasi.

- **Dashboard Visualisasi Chart.js (`/dashboard`):**
  - Ringkasan statistik sistem, distribusi sentimen repositori pantau, dan log alert terbaru.
  - Panel evaluasi model (scatter plot Model B aktual vs prediksi, metrik CV, dan temuan empiris durasi).
  - Status proses penjadwal harian.

- **Panel Administrasi Terproteksi (`/admin`):**
  - Manajemen repositori pantau (tambah, aktif/nonaktifkan) dan daftar repositori latih.
  - Pengaturan ambang batas sensitivitas tier alert (lemah, sedang, kuat).
  - Scraping manual terisolasi, audit log percakapan, log scheduler, dan manajemen subscriber bot.

- **Kartu Kesehatan Repositori (`/kesehatan`):**
  - Penilaian kesehatan komprehensif mengintegrasikan metrik kecepatan (durasi elapsed vs estimasi), beban kerja per anggota, dan sentimen 14 hari terakhir.
  - Indikator visual hijau/kuning/merah disertai alasan transparan dan *disclaimer* batas interpretasi.

---

## Teknologi

- **Bahasa & Runtime:** Python 3.10+
- **Framework Web:** Flask, Jinja2, HTML5/CSS3, JavaScript
- **Visualisasi Data:** Chart.js
- **Database:** SQLite3 dengan mode Write-Ahead Logging (WAL)
- **Machine Learning & Statistik:** scikit-learn, NumPy, pandas, scipy (Spearman Rank)
- **Pemrosesan Bahasa Alami:** vaderSentiment (dengan aturan teknis kustom)
- **Integrasi Eksternal:** GitHub REST API v3, Git CLI via `subprocess`
- **Bot & Penjadwalan:** python-telegram-bot (v20+ async/polling), APScheduler
- **Pengujian:** pytest (100% lulus, 97 tes)

---

## Instalasi dan Konfigurasi

### 1. Kloning Repositori & Persiapan Lingkungan
```bash
git clone https://github.com/<owner>/ProjectPulse.git
cd ProjectPulse

# Buat virtual environment
python -m venv venv

# Aktivasi virtual environment:
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Linux / macOS:
source venv/bin/activate

# Pasang dependensi
pip install -r requirements.txt
```

### 2. Konfigurasi Variabel Lingkungan (`.env`)
Salin berkas template `.env.example` menjadi `.env`:
```bash
copy .env.example .env     # Windows
cp .env.example .env       # Linux / macOS
```

Buka berkas `.env` dan sesuaikan parameter berikut:
```ini
# Rahasia Flask session
SECRET_KEY=ganti-dengan-kunci-rahasia-acak

# Token GitHub (cukup izin read-only data publik)
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Token Bot Telegram dari @BotFather
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Password panel admin web (/admin/login)
ADMIN_PASSWORD=admin123

# Pengaturan Penjadwal
SCHEDULER_HOUR=6
SCHEDULER_MINUTE=0
TIMEZONE=Asia/Jakarta

# Kapasitas data
MAX_COMMENTS_PER_REPO=500
```

> [!WARNING]
> Jangan pernah membagikan atau meng-commit token GitHub atau bot Telegram Anda ke dalam repositori publik.

---

## Cara Menjalankan Tiga Proses Terpisah

ProjectPulse dirancang berjalan dalam **tiga proses terpisah** yang dapat dioperasikan secara mandiri di tiga terminal berbeda:

### Proses 1: Aplikasi Web (Flask)
Menjalankan server antarmuka web, dashboard analitik, formulir estimasi, chatbot web, dan panel admin.
```bash
python -m app.web
```
Akses melalui browser di: `http://localhost:5000`

### Proses 2: Bot Telegram (Polling)
Menjalankan bot Telegram ProjectPulse untuk menerima perintah interaktif, mengelola watchlist pengguna, dan mengirim pesan ringkasan.
```bash
python -m app.bot
```

### Proses 3: Penjadwal Latar Belakang (APScheduler)
Menjalankan proses daemon harian yang otomatis mengeksekusi scraping komentar repositori, evaluasi alert, dan pengiriman *daily digest* ke Telegram pada jam yang ditentukan (`SCHEDULER_HOUR` & `SCHEDULER_MINUTE`).
```bash
python -m app.scheduler
```

---

## Panduan Antarmuka CLI

Perintah CLI dijalankan menggunakan format `python -m app.cli <perintah>`:

| Perintah | Deskripsi |
| :--- | :--- |
| `init-db` | Menginisialisasi skema tabel database SQLite dan data awal repositori pantau. |
| `build-training-data` | Mengklon dan mengekstrak metrik git/issue dari daftar `data/training_repos.json`. |
| `train-models` | Melatih Model A & B, menghitung metrik validasi silang, dan membangun benchmark durasi. |
| `run-cycle` | Menjalankan satu siklus penuh: scraping repositori, kalkulasi alert, dan pengiriman notifikasi. |
| `validate-sentiment` | Mengevaluasi performa VADER (akurasi, F1, matriks konfusi) terhadap label manual. |
| `rescore` | Menghitung ulang label sentimen seluruh komentar di database sesuai leksikon terkini. |
| `export-comments` | Mengekspor sampel komentar acak ke format CSV untuk persiapan pelabelan manual. |
| `list-subscribers` | Menampilkan daftar pengguna yang berlangganan bot Telegram dan daftar pantauannya. |

---

## Urutan Kerja Pemilik (Owner Workflow)

Untuk mempersiapkan data awal dan model estimasi dari nol, ikuti urutan kerja berikut:

1. **Inisialisasi Database:**
   ```bash
   python -m app.cli init-db
   ```
2. **Pengisian Daftar Repositori Latih:**
   Pemilik mengisi berkas `data/training_repos.json` dengan daftar 30–60 repositori open-source publik (bukan repositori pantau).
3. **Ekstraksi Data Latih GitHub:**
   ```bash
   python -m app.cli build-training-data
   ```
   *Metrik commit pertama, rilis stabil pertama, kontributor, issue/PR, dan KLOC akan diekstrak dan disimpan ke database serta `data/training_dataset.csv`.*
4. **Pelatihan Model & Pembentukan Benchmark:**
   ```bash
   python -m app.cli train-models
   ```
   *Melatih regresi NASA93 (Model B) dan regresi GitHub (Model A), lalu menyimpan ringkasan evaluasi ke `models/metrics_a.json` dan `models/metrics_b.json`.*
5. **Ekspor Sampel Komentar untuk Pelabelan Sentimen:**
   Setelah proses scraping berjalan pada repositori pantau, ekspor sampel komentar:
   ```bash
   python -m app.cli export-comments --n 100
   ```
6. **Pelabelan Manual oleh Pemilik:**
   Buka berkas hasil ekspor dan berikan label `positif`, `netral`, atau `negatif` pada kolom label, lalu simpan sebagai `data/labels/sentiment_labels.csv`.
7. **Validasi Model Sentimen:**
   ```bash
   python -m app.cli validate-sentiment
   ```
   *Hasil validasi akan tersimpan di `models/sentiment_validation.json` dan langsung ditampilkan pada halaman Pulse Repositori.*

---

## Temuan Evaluasi Durasi GitHub & Keputusan Model

Evaluasi model regresi linier durasi kalender dari repositori open source GitHub (**Model A**) pada dataset latih empiris menunjukkan **tidak adanya kemampuan prediksi yang memadai**:

- **Akurasi Validasi Silang (Repeated 5-Fold, 20x):**
  - **MAE Model A:** `3.80 bulan` (varian log1p) vs **Baseline Tebak Median:** `3.50 bulan`.
  - **Peningkatan (*Improvement Pct*):** `-8.63%` (prediksi model regresi linier secara konsisten lebih buruk dibanding sekadar menebak nilai median durasi historis).
- **$R^2$ Validasi Silang Out-of-Fold:**
  - $R^2$ bernilai negatif (`-0.5633`), mengonfirmasi bahwa varians durasi rilis kalender tidak dapat dijelaskan secara reliabel oleh metrik ukuran kumulatif (kontributor, work items, KLOC).
- **Korelasi Spearman Kontributor Kumulatif:**
  - Korelasi antara durasi dan jumlah kontributor bernilai lemah ($\rho = 0.155$). Korelasi positif yang muncul pada data historis mencerminkan **faktor usia proyek** (proyek yang hidup lebih lama secara alami mengumpulkan lebih banyak kontributor kumulatif), bukan hubungan sebab-akibat bahwa menambah anggota mempercepat durasi proyek.

### Keputusan Arsitektur:
1. **Halaman `/estimasi` hanya menggunakan Model B (NASA93 COCOMO 81)** untuk memprediksi usaha (*person-months*) dan durasi kalender indikatif. Model A **tidak digunakan sebagai prediktor estimasi**.
2. **Data GitHub difungsikan sebagai Benchmark Empiris**: disajikan sebagai pembanding durasi rilis stabil pertama (median dan rentang interkuartil Q1–Q3) serta analisis persentil beban kerja tim.
3. **Pemisahan Tesis Kecepatan vs Suasana**: Evaluasi kesehatan proyek pada `/kesehatan` memadukan kecepatan proyek dan sentimen komunitas. **Catatan:** hubungan statistik antara sentimen komunitas dan keterlambatan rilis belum diuji secara empiris dalam proyek ini dan dicatat sebagai agenda pekerjaan lanjutan.

---

## Keterbatasan Proyek

Sebagai bagian dari integritas ilmiah dan rekayasa perangkat lunak, pengguna harus memahami keterbatasan sistem berikut:

1. **Model A Menangkap Korelasi Historis Usia Proyek:** Jumlah kontributor kumulatif bertambah seiring berjalannya waktu. Model ini tidak memodelkan efek penambahan anggota tim terhadap percepatan durasi (Hukum Brooks: *adding manpower to a late software project makes it later*).
2. **Durasi Kalender Bukan Waktu Kerja Efektif:** Durasi dihitung dari rentang tanggal commit pertama hingga rilis pertama di GitHub. Metrik ini mencakup masa dorman, libur, dan waktu idle pengembang sukarelawan, bukan jam kerja kerja riil (*effort*).
3. **Representasi Repositori Open Source:** Repositori publik open source memiliki tata kelola sukarela, kontributor paruh waktu, dan siklus rilis yang sangat berbeda dibandingkan proyek mahasiswa atau tim industri kecil terstruktur.
4. **Variabel Non-Teknis Tidak Terukur:** Model estimasi tidak menerima input mengenai keahlian teknis individu, tingkat komunikasi, maupun metodologi kerja (Scrum/Agile/Waterfall).
5. **Keterbatasan Dataset NASA93:** Hanya mencakup 93 proyek historis industri kedirgantaraan era 1970–1980-an dengan distribusi miring (*skewed*) dan tidak mencakup proyek skala mikro modern.
6. **Asumsi Model COCOMO:** Pengali usaha dan durasi COCOMO 81 adalah model parametrik berbasis asumsi empiris industri klasik.
7. **Perhitungan KLOC yang Disederhanakan:** KLOC dihitung secara leksikal dari baris berkas kode sumber yang relevan (termasuk baris komentar dan baris kosong di dalamnya) tanpa menggunakan kakas parser khusus seperti `cloc`.
8. **Proksi Aktivitas:** Jumlah kontributor commit dan gabungan issue/PR adalah proksi kasar aktivitas kerja, bukan ukuran produktivitas langsung.
9. **Batas Laju GitHub API (*Rate Limit*):** Panggilan API dibatasi 60 permintaan/jam (tanpa token) atau 5.000 permintaan/jam (dengan personal access token).
10. **Sifat Alert Harian (*Batch*):** Alert dievaluasi secara berkala oleh penjadwal harian, bukan notifikasi instan real-time (bukan berbasis webhook streaming).
11. **Ketersediaan Layanan Lokal:** Bot Telegram dan Penjadwal hanya aktif saat komputer induk atau server lokal berjalan.
12. **Keterbatasan Perintah `rescore`:** Menilai ulang sentimen seluruh komentar di tabel `comments`, namun tidak mengubah data agregat ringkasan historis di `daily_stats`.
13. **Ketiadaan Ground Truth Otomatis Sentimen:** GitHub tidak menyediakan rating bintang atau sentimen biner pada komentar; evaluasi akurasi sentimen murni bersandar pada sampel label manual yang disediakan pemilik.
14. **Korelasi Sentimen vs Keterlambatan Belum Teruji Empiris:** Walaupun disajikan berdampingan pada Kartu Kesehatan Repositori, hubungan kausalitas atau korelasi statistik antara penurunan sentimen dan keterlambatan rilis belum diuji secara formal dalam penelitian ini (pekerjaan lanjutan).

---

## Sumber Data

1. **GitHub REST API v3 & Git VCS:**
   - Data riwayat commit, tag rilis, issue, pull request, dan komentar publik.
2. **NASA93 Software Cost Estimation Dataset:**
   - Dataset publik 93 proyek rekayasa perangkat lunak NASA/industri untuk kalibrasi model usaha COCOMO.
3. **COCOMO 81 (Constructive Cost Model):**
   - Barry W. Boehm, *Software Engineering Economics*, Prentice-Hall, 1981.

---

*ProjectPulse — Dibuat untuk pemenuhan tugas akhir praktikum Aplikasi Web & Scripting Language.*
