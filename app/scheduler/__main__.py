"""Titik masuk eksekusi Penjadwal Scraping & Alert: python -m app.scheduler."""
import sys

if __name__ == "__main__":
    print("Penjadwal Scraping & Alert ProjectPulse (tersedia pada Milestone M4).")
    if "--once" in sys.argv:
        print("Mode --once: satu siklus selesai.")
