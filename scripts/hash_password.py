"""Skrip utilitas untuk menghasilkan hash password admin menggunakan Werkzeug."""
import sys
import getpass
from werkzeug.security import generate_password_hash


def main() -> None:
    """Meminta password dan mencetak nilai hash untuk disimpan di .env."""
    if len(sys.argv) > 1:
        raw_password = sys.argv[1]
    else:
        raw_password = getpass.getpass("Masukkan password admin: ")

    if not raw_password:
        print("Error: Password tidak boleh kosong.")
        sys.exit(1)

    hashed = generate_password_hash(raw_password)
    print("\nSalin nilai berikut ke ADMIN_PASSWORD_HASH di berkas .env:")
    print(f"ADMIN_PASSWORD_HASH='{hashed}'")


if __name__ == "__main__":
    main()
