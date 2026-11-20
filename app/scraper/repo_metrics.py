"""Modul ekstraksi metrik git dan kalkulasi KLOC untuk ProjectPulse."""
from __future__ import annotations

import io
import re
import subprocess
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Any

from app import config

SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift",
    ".scala", ".sh", ".vue", ".svelte", ".dart", ".lua", ".ex", ".exs",
    ".hs", ".clj",
})

EXCLUDED_DIRS: frozenset[str] = frozenset({
    "node_modules", "vendor", "third_party", "dist", "build", "out",
    "target", ".next", "coverage", "__pycache__", "site-packages",
    "packages", "_vendor", "vendored", "bundled",
})

MAX_FILE_BYTES: int = 2 * 1024 * 1024  # 2 MB


class GitCommandError(Exception):
    """Pengecualian saat eksekusi perintah git CLI gagal."""


def validate_repo_name(full_name: str) -> bool:
    """Memvalidasi format nama repositori: pemilik/nama."""
    if not isinstance(full_name, str):
        return False
    return bool(re.match(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$", full_name.strip()))


class GitRunner:
    """Menjalankan perintah eksternal git secara aman via subprocess."""

    def __init__(self, timeout: float = 120.0) -> None:
        self.timeout = timeout

    def run(self, args: list[str], cwd: Path | str | None = None) -> str:
        """Mengeksekusi perintah git dengan argumen berupa list (tanpa shell)."""
        cmd = ["git"] + args
        try:
            res = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                check=False,
            )
        except Exception as err:
            raise GitCommandError(f"Gagal menjalankan perintah git: {err}")

        if res.returncode != 0:
            stderr_cleaned = res.stderr.strip()
            raise GitCommandError(f"Perintah git gagal (kode {res.returncode}): {stderr_cleaned}")
        return res.stdout.strip()


def parse_semver(tag: str) -> tuple[int, int, int] | None:
    """Memvalidasi dan mem-parsing semver murni tanpa pre-release (MAJOR >= 1)."""
    clean_tag = tag.strip().lstrip("v")
    match = re.match(r"^([1-9]\d*)\.(\d+)(?:\.(\d+))?$", clean_tag)
    if not match:
        return None
    major, minor, patch = match.group(1), match.group(2), match.group(3)
    return (int(major), int(minor), int(patch) if patch is not None else 0)


def find_first_stable_release_tag(tag_entries: list[tuple[str, str]]) -> str | None:
    """Memilih tag rilis stabil pertama (commit paling awal; jika seri -> versi terkecil)."""
    valid_tags: list[tuple[str, tuple[int, int, int], str]] = []
    for tag, commit_date in tag_entries:
        parsed = parse_semver(tag)
        if parsed:
            valid_tags.append((commit_date, parsed, tag))

    if not valid_tags:
        return None

    # Urutkan berdasarkan tanggal commit menaik, lalu semver menaik
    valid_tags.sort(key=lambda x: (x[0], x[1]))
    return valid_tags[0][2]


def first_commit_date(repo_dir: Path, runner: GitRunner | None = None) -> str:
    """Mengambil tanggal commit pertama (akar paling awal) dalam format ISO."""
    r = runner or GitRunner()
    roots = r.run(["rev-list", "--max-parents=0", "HEAD"], cwd=repo_dir).split()
    if not roots:
        raise GitCommandError("Tidak ditemukan commit pada repositori.")

    earliest_dt: str | None = None
    for commit_hash in roots:
        date_str = r.run(["log", "-1", "--format=%aI", commit_hash], cwd=repo_dir)
        if not earliest_dt or date_str < earliest_dt:
            earliest_dt = date_str
    return earliest_dt or ""


def release_date(repo_dir: Path, tag: str, runner: GitRunner | None = None) -> str:
    """Mengambil tanggal committer dari tag rilis dalam format ISO."""
    r = runner or GitRunner()
    return r.run(["log", "-1", "--format=%cI", f"{tag}^{{commit}}"], cwd=repo_dir)


def is_bot(name: str, email: str) -> bool:
    """Memeriksa apakah akun penulis commit merupakan bot."""
    lower_name = name.lower()
    lower_email = email.lower()
    if "[bot]" in lower_name or "[bot]" in lower_email:
        return True
    for ignored in config.IGNORED_LOGINS:
        if ignored in lower_name or ignored in lower_email:
            return True
    return False


def contributors_until(repo_dir: Path, ref: str, runner: GitRunner | None = None) -> int:
    """Menghitung jumlah penulis commit unik (non-bot) sampai referensi tertentu."""
    r = runner or GitRunner()
    raw = r.run(["log", "--format=%an\t%ae", ref], cwd=repo_dir)
    authors: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        name = parts[0] if len(parts) > 0 else ""
        email = parts[1] if len(parts) > 1 else ""
        if not is_bot(name, email) and email:
            authors.add(email.lower())
    return len(authors)


def should_count_file(file_path: str, size: int) -> bool:
    """Menentukan apakah berkas kode sumber layak dihitung baris kodenya."""
    if size > MAX_FILE_BYTES:
        return False
    p = Path(file_path)
    if p.suffix.lower() not in SOURCE_EXTENSIONS:
        return False
    if file_path.endswith(".min.js") or file_path.endswith(".d.ts"):
        return False
    parts = p.parts
    return not any(d in EXCLUDED_DIRS for d in parts)


def count_non_empty_lines(content: bytes) -> int:
    """Menghitung baris tidak kosong dari byte teks kode sumber."""
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return 0
    return sum(1 for line in text.splitlines() if line.strip())


def kloc_at(repo_dir: Path, ref: str, runner: GitRunner | None = None) -> float:
    """Menghitung ribuan baris kode sumber (KLOC) pada referensi tag/commit tertentu."""
    r = runner or GitRunner()
    cmd = ["git", "archive", "--format=tar", ref]
    proc = subprocess.Popen(
        cmd,
        cwd=str(repo_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    total_lines = 0
    try:
        with tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
            for member in tar:
                if not member.isfile():
                    continue
                if should_count_file(member.name, member.size):
                    f = tar.extractfile(member)
                    if f:
                        total_lines += count_non_empty_lines(f.read())
        proc.wait(timeout=120)
    finally:
        if proc.poll() is None:
            proc.kill()
    return round(total_lines / 1000.0, 3)


def calculate_duration_months(first_commit_iso: str, release_date_iso: str) -> float:
    """Menghitung durasi kalender bulan antara dua tanggal ISO (30.4375 hari/bulan)."""
    dt1 = datetime.fromisoformat(first_commit_iso.replace("Z", "+00:00"))
    dt2 = datetime.fromisoformat(release_date_iso.replace("Z", "+00:00"))
    diff_days = (dt2 - dt1).total_seconds() / 86400.0
    return round(diff_days / 30.4375, 2)
