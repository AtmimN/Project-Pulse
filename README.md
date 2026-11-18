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

## Status
Dalam pengembangan. Spesifikasi lengkap ada di [`instruction.md`](instruction.md) dan [`docs/instruction/`](docs/instruction/).

> README ini akan dilengkapi di akhir pengembangan (instalasi dan cara menjalankan).
