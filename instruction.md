# instruction.md — Panduan Pembangunan ProjectPulse

> Berkas ini adalah **pintu masuk**. Baca seluruhnya, lalu baca berkas di `docs/instruction/` sesuai urutan pada bagian 4. Semua spesifikasi rinci ada di sana.

## 0. Peran dan Prinsip Kerja

Kamu adalah software engineer Python/Flask senior yang juga menjadi mentor bagi seorang mahasiswa. Kodenya akan dibaca dan dipertanggungjawabkan oleh mahasiswa tersebut di depan dosen, jadi kode harus **mudah dibaca, rapi, dan bisa dijelaskan**.

Prinsip kerja:

1. **Pelajari referensi dulu.** Baca `reference/PM-Bot/` sampai paham sebelum menulis kode. Folder itu **hanya dibaca**: jangan diubah, dihapus, atau dijadikan tempat menulis kode baru.
2. **Tulis sendiri, bukan salin.** Kode ProjectPulse ditulis di `app/`. Kamu boleh mengadaptasi logika PM-Bot (mesin chatbot, format intent, pola admin, pola pengujian), tetapi sesuaikan dengan struktur baru dan jangan menyalin berkas mentah-mentah.
3. **Sederhana dulu.** Pilih solusi paling sederhana yang memenuhi spesifikasi. Jangan menambah fitur, lapisan abstraksi, atau dependensi yang tidak diminta.
4. **Jangan menebak dan jangan mengarang data.** Jika informasi penting hilang (berkas NASA93 belum ada, daftar repositori latih kosong, label sentimen belum ada, token belum diisi), berhenti pada bagian itu, laporkan, dan gunakan solusi sementara yang jelas diberi label. Dilarang mengisi daftar repositori latih, mengarang angka repositori, atau memakai nilai dari ingatan sebagai pengganti data yang diminta dari berkas.
5. **Jujur soal hasil pengujian.** Jangan menulis "semua tes lulus" sebelum benar-benar menjalankannya. Laporkan hasil apa adanya, termasuk yang gagal.
6. **Jangan menjalankan `git commit` atau `git push`** pada repositori proyek ini. Pemilik repositori melakukannya sendiri. (Perintah `git` untuk mengukur repositori lain, di dalam kode aplikasi, adalah hal berbeda dan diatur di `04`.)
7. **Jangan melakukan akses jaringan sungguhan tanpa diminta**: tidak memanggil GitHub API, tidak meng-*clone* repositori, tidak menjalankan bot Telegram. Pengujian memakai data, klien, dan repositori git lokal tiruan. Token tidak dipakai di tes.
8. **Laporan akhir ringkas.** Setiap kali selesai satu milestone, beri ringkasan 3–6 baris: apa yang dibuat, cara menjalankan, hasil tes, dan hal yang perlu keputusan pemilik.

## 1. Konteks dan Tujuan

**ProjectPulse** adalah aplikasi untuk **dua mata kuliah sekaligus** (Aplikasi Web dan Scripting Language): satu project gabungan dengan dua sisi, yang bersumber dari **satu sumber data yang sama: repositori publik GitHub**.

- **Sisi web (Flask):** chatbot rule-based PM-Bot, estimasi durasi proyek (dua model regresi berdampingan), halaman sentimen komentar (Pulse Repositori), dan dashboard Chart.js.
- **Sisi scripting (otomatisasi):** penjadwal scraping harian data repositori pantau, mesin alert, dan bot Telegram yang mengirim alert serta ringkasan harian.

Tesis: ProjectPulse menilai kesehatan sebuah proyek dari dua sisi: **kecepatan** (estimasi durasi) dan **suasana tim/pengguna** (sentimen komentar).

Kunci rancangan:
- **Satu scraper mengisi satu database.** Chatbot, estimasi, sentimen, dashboard, dan bot Telegram hanya membaca database itu.
- **Dua jenis repositori yang tidak boleh beririsan:** *repositori latih* (30–60 repositori dengan kriteria tertulis, dipakai melatih Model A, diproses sebagai batch) dan *repositori pantau* (sedikit, dipakai untuk sentimen dan alert, di-scrape harian).

| Materi | Penerapan |
|---|---|
| Chatbot tematik rule-based | PM-Bot (dikembangkan dari referensi), membaca hasil dari database |
| Linear regression | Model A (data repositori GitHub: durasi) dan Model B (NASA93: usaha), ditampilkan berdampingan |
| Sentiment analysis | Komentar issue dan pull request berbahasa Inggris |
| Visualisasi data (Flask) | Dashboard Chart.js |
| Scraping terjadwal (Scripting) | Penjadwal harian incremental: hanya komentar dan rilis baru |
| Bot Telegram (Scripting) | Watchlist repositori, alert, digest harian, ringkasan, perbandingan |

## 2. Berkas yang Sudah Disediakan

| Berkas / folder | Keterangan |
|---|---|
| `reference/PM-Bot/` | Aplikasi chatbot sebelumnya. **Hanya dibaca.** Ambil mesin chatbot, format intent, pola admin dan pengujian. **Jangan bawa fitur menambah tema.** |
| `data/monitor_repos.json` | Daftar awal repositori pantau (3 repositori). |
| `data/training_repos.json` | Kriteria repositori latih; daftar `repos` **diisi pemilik**. |
| `data/nasa93/` | Tempat berkas NASA93 (diisi pemilik). |
| `data/labels/` | Tempat label sentimen manual (dibuat pemilik). |
| `.gitignore`, `README.md` | Kerangka awal. README final ditulis di milestone terakhir. |

## 3. Cakupan

**Dalam cakupan:** chatbot, pipeline data repositori latih, dua model regresi dan halaman estimasi berdampingan, scraper komentar dan rilis repositori pantau, analisis sentimen Inggris dengan validasi sampel manual, mesin alert (4 jenis) dan uji ulang (backtest), bot Telegram, halaman Pulse Repositori, dashboard, admin dan pemantauan, pengujian, README.

**Di luar cakupan:** fitur menambah atau memilih tema chatbot, registrasi pengguna web umum, evaluasi akurasi chatbot (`evaluate`), webhook Telegram dan deployment ke server, notifikasi real-time, model deep learning, sumber data selain GitHub dan NASA93, pendaftaran repositori pantau oleh pengguna bot (daftar diatur admin), bot di grup Telegram.

## 4. Urutan Membaca

1. `docs/instruction/01-arsitektur.md` — teknologi, proses, struktur folder, aturan kode bersih
2. `docs/instruction/02-chatbot.md`
3. `docs/instruction/03-estimasi-regresi.md`
4. `docs/instruction/04-data-github-sentimen.md`
5. `docs/instruction/05-dashboard-admin.md`
6. `docs/instruction/06-bot-telegram.md`
7. `docs/instruction/07-penjadwal-alert.md`
8. `docs/instruction/09-pengujian-dod.md` — kasus uji dan Definition of Done
9. `docs/instruction/08-git-workflow.md` — catatan untuk pemilik repositori (AI cukup membaca daftar milestone)

## 5. Urutan Pengerjaan

Kerjakan berurutan. Setelah tiap milestone selesai, **berhenti sebentar dan beri ringkasan** supaya pemilik repositori bisa melakukan commit.

| Milestone | Isi | Selesai jika |
|---|---|---|
| M0 | Kerangka proyek: struktur folder, `requirements.txt`, `create_app`, konfigurasi, skema database (mode WAL), CLI | Aplikasi kosong berjalan dan halaman beranda tampil |
| M1 | Chatbot dipindahkan dari PM-Bot (tanpa tema) + intent baru + halaman chat | Tes chatbot lulus dan halaman chat berfungsi |
| M2 | Pipeline data repositori latih (klien GitHub, metrik git, KLOC), Model A, Model B (NASA93), halaman estimasi berdampingan | Tes lulus dengan repositori git lokal tiruan; pelatihan Model B jalan jika NASA93 ada |
| M3 | Sentimen Inggris (+ validasi) dan scraper komentar/rilis incremental dengan batas data | Tes sentimen dan scraping lulus (klien tiruan) |
| M4 | Mesin alert + penjadwal (harian + susulan) + log eksekusi + backtest alert | Tes alert dan penjadwal lulus |
| M5 | Bot Telegram: perintah, notifier, digest harian | Tes bot lulus dengan klien tiruan |
| M6 | Halaman Pulse Repositori, dashboard Chart.js, admin dan pemantauan | Semua halaman dan grafik berfungsi |
| M7 | Pengujian menyeluruh, README final, tinjauan akhir | Semua centang di `09-pengujian-dod.md` terpenuhi |

## 6. Laporan Akhir

Setelah M7, tulis laporan singkat (maksimal 20 baris): cara menjalankan dari nol (tiga proses dan perintah CLI), hasil tes sebenarnya, keterbatasan yang diketahui, dan hal yang perlu diputuskan pemilik.
