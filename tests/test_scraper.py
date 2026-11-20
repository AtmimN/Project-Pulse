"""Pengujian modul penarik data git lokal dan klien GitHub API."""
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.scraper.github_client import (
    AuthError,
    GitHubClient,
    GitHubError,
    RateLimitError,
    RepoNotFoundError,
)
from app.scraper.repo_metrics import (
    GitRunner,
    calculate_duration_months,
    contributors_until,
    find_first_stable_release_tag,
    first_commit_date,
    kloc_at,
    parse_semver,
    release_date,
    validate_repo_name,
)


def test_validate_repo_name() -> None:
    """Memvalidasi aturan penamaan repositori GitHub."""
    assert validate_repo_name("owner/repo") is True
    assert validate_repo_name("psf/requests") is True
    assert validate_repo_name("chartjs/chart.js") is True
    assert validate_repo_name("Yelp/detect-secrets") is True

    assert validate_repo_name("invalid") is False
    assert validate_repo_name("owner/repo/extra") is False
    assert validate_repo_name("../hack/repo") is False
    assert validate_repo_name("") is False


def test_semver_and_first_stable_release() -> None:
    """Memastikan pemilihan tag rilis stabil pertama mengikuti aturan semver murni."""
    assert parse_semver("v1.0.0") == (1, 0, 0)
    assert parse_semver("1.0") == (1, 0, 0)
    assert parse_semver("v2.3.4") == (2, 3, 4)
    assert parse_semver("v0.9.0") is None  # Major < 1
    assert parse_semver("v1.0.0-rc1") is None  # Pre-release
    assert parse_semver("beta-1.0") is None

    # Kasus: v0.9.0, v1.0.0-rc1, v1.0.0, v1.1.0 -> memilih v1.0.0
    entries = [
        ("v0.9.0", "2024-01-01T00:00:00Z"),
        ("v1.0.0-rc1", "2024-02-01T00:00:00Z"),
        ("v1.0.0", "2024-03-01T00:00:00Z"),
        ("v1.1.0", "2024-04-01T00:00:00Z"),
    ]
    assert find_first_stable_release_tag(entries) == "v1.0.0"

    # Kasus bentuk dua bagian: 0.9, 1.0, 1.1 -> memilih 1.0
    entries_two = [
        ("0.9", "2024-01-01T00:00:00Z"),
        ("1.0", "2024-02-01T00:00:00Z"),
        ("1.1", "2024-03-01T00:00:00Z"),
    ]
    assert find_first_stable_release_tag(entries_two) == "1.0"

    # Tanpa rilis stabil
    assert find_first_stable_release_tag([("v0.1", "2024-01-01")]) is None


def test_git_metrics_with_local_repo(tmp_path: Path) -> None:
    """Menguji kalkulasi metrik git (commit awal, kontributor non-bot, KLOC) pada git tiruan."""
    repo_dir = tmp_path / "mock_repo"
    repo_dir.mkdir()

    runner = GitRunner()
    runner.run(["init"], cwd=repo_dir)
    runner.run(["config", "user.name", "Dev One"], cwd=repo_dir)
    runner.run(["config", "user.email", "dev1@example.com"], cwd=repo_dir)

    # Commit 1 (akar)
    src_file = repo_dir / "app.py"
    src_file.write_text("print('hello world')\nx = 1\n\ny = 2\n", encoding="utf-8")
    runner.run(["add", "."], cwd=repo_dir)
    runner.run(["commit", "-m", "Initial commit"], cwd=repo_dir)

    # Commit 2 oleh kontributor lain dengan karakter non-ASCII (UTF-8)
    runner.run(["config", "user.name", "Jürgen ⚡ Developer"], cwd=repo_dir)
    runner.run(["config", "user.email", "jurgen@example.com"], cwd=repo_dir)
    js_file = repo_dir / "script.js"
    js_file.write_text("console.log('js');\nconst a = 10;\n", encoding="utf-8")
    runner.run(["add", "."], cwd=repo_dir)
    runner.run(["commit", "-m", "Add js file with ütf8 commit msg"], cwd=repo_dir)

    # Commit oleh akun bot (harus diabaikan dari kontributor)
    runner.run(["config", "user.name", "dependabot[bot]"], cwd=repo_dir)
    runner.run(["config", "user.email", "dependabot[bot]@users.noreply.github.com"], cwd=repo_dir)
    dummy = repo_dir / "dummy.py"
    dummy.write_text("a = 1\n", encoding="utf-8")
    runner.run(["add", "."], cwd=repo_dir)
    runner.run(["commit", "-m", "Bump dependency"], cwd=repo_dir)

    # Berkas di direktori yang dikecualikan (node_modules dan .min.js)
    nm_dir = repo_dir / "node_modules"
    nm_dir.mkdir()
    (nm_dir / "dep.js").write_text("\n".join(f"line_{i} = {i};" for i in range(500)), encoding="utf-8")
    (repo_dir / "bundle.min.js").write_text("console.log('min');\n", encoding="utf-8")
    runner.run(["add", "."], cwd=repo_dir)
    runner.run(["commit", "-m", "Add vendored files"], cwd=repo_dir)

    # Tag rilis stabil
    runner.run(["tag", "v1.0.0"], cwd=repo_dir)

    # Commit setelah rilis (tidak boleh ikut dihitung pada tag v1.0.0)
    runner.run(["config", "user.name", "Dev Three"], cwd=repo_dir)
    runner.run(["config", "user.email", "dev3@example.com"], cwd=repo_dir)
    (repo_dir / "after_release.py").write_text("extra = 99\n", encoding="utf-8")
    runner.run(["add", "."], cwd=repo_dir)
    runner.run(["commit", "-m", "Post release commit"], cwd=repo_dir)

    # Validasi metrik
    first_dt = first_commit_date(repo_dir, runner)
    assert len(first_dt) > 0

    rel_dt = release_date(repo_dir, "v1.0.0", runner)
    assert len(rel_dt) > 0

    # Kontributor sampai tag: hanya Dev One & Dev Two (Dev Three setelah tag, dependabot bot)
    n_contrib = contributors_until(repo_dir, "v1.0.0", runner)
    assert n_contrib == 2

    # KLOC pada tag v1.0.0 (app.py: 3 baris, script.js: 2 baris, dummy.py: 1 baris = 6 baris = 0.006 KLOC)
    # node_modules dan bundle.min.js tidak ikut terhitung
    kloc = kloc_at(repo_dir, "v1.0.0", runner)
    assert kloc == 0.006

    dur = calculate_duration_months("2024-01-01T00:00:00+00:00", "2024-03-01T00:00:00+00:00")
    assert dur > 1.8


def test_github_client_error_handling(monkeypatch) -> None:
    """Menguji penanganan batas laju (RateLimitError), 401 (AuthError), dan 404 (RepoNotFoundError)."""
    client = GitHubClient(token="secret-dummy-token")

    class FakeResponse:
        def __init__(self, status_code: int, headers: dict, text: str = "") -> None:
            self.status_code = status_code
            self.headers = headers
            self.text = text

        def json(self):
            return {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise Exception(f"HTTP {self.status_code}")

    # 1. RateLimitError ketika sisa 0
    monkeypatch.setattr(
        client.session,
        "request",
        lambda *args, **kwargs: FakeResponse(403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"}, "rate limit exceeded"),
    )
    with pytest.raises(RateLimitError) as exc_rl:
        client.get_repo("psf/requests")
    assert "secret-dummy-token" not in str(exc_rl.value)

    # 2. 401 AuthError
    monkeypatch.setattr(
        client.session,
        "request",
        lambda *args, **kwargs: FakeResponse(401, {}, "Bad credentials"),
    )
    with pytest.raises(AuthError) as exc_auth:
        client.get_repo("psf/requests")
    assert "secret-dummy-token" not in str(exc_auth.value)

    # 3. 404 RepoNotFoundError
    monkeypatch.setattr(
        client.session,
        "request",
        lambda *args, **kwargs: FakeResponse(404, {}, "Not Found"),
    )
    with pytest.raises(RepoNotFoundError):
        client.get_repo("notfound/unknown-repo")
