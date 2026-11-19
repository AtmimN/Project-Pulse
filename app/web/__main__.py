"""Titik masuk eksekusi server web: python -m app.web."""
from app.web import create_app

if __name__ == "__main__":
    app = create_app()
    print("Menjalankan server web ProjectPulse pada http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True)
