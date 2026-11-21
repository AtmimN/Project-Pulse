"""Klien tipis GitHub API v3 berbasis requests untuk ProjectPulse."""
from __future__ import annotations

import re
import time
from typing import Any
import requests

from app import config


class GitHubError(Exception):
    """Pengecualian umum untuk kesalahan permintaan GitHub API."""


class RateLimitError(GitHubError):
    """Batas laju permintaan GitHub API telah habis."""

    def __init__(self, message: str, reset_at: int | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class AuthError(GitHubError):
    """Autentikasi token GitHub gagal (401 Unauthorized)."""


class RepoNotFoundError(GitHubError):
    """Repositori tidak ditemukan di GitHub (404 Not Found)."""


class GitHubClient:
    """Klien pembungkus permintaan REST API ke GitHub."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.token = token if token is not None else config.GITHUB_TOKEN

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ProjectPulse/1.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self.session.headers.update(headers)

    def _check_rate_limit(self, response: requests.Response) -> None:
        """Memeriksa sisa kuota permintaan dari header respons GitHub."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_time = response.headers.get("X-RateLimit-Reset")
        reset_int = int(reset_time) if reset_time and reset_time.isdigit() else None

        if remaining is not None and remaining == "0":
            raise RateLimitError(
                f"Batas laju GitHub API habis. Reset pada timestamp {reset_int}.",
                reset_at=reset_int,
            )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Mengirim permintaan HTTP dengan penanganan timeout, rate limit, dan retry."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = self.session.request(method, url, params=params, timeout=30.0)
                self._check_rate_limit(response)

                if response.status_code == 401:
                    raise AuthError("Token GitHub tidak valid atau tidak memiliki izin.")
                if response.status_code == 404:
                    raise RepoNotFoundError(f"Repositori atau sumber daya tidak ditemukan: {endpoint}")
                if response.status_code == 403 and "rate limit" in response.text.lower():
                    raise RateLimitError("Akses ditolak: Batas laju GitHub API terlampaui.")

                if response.status_code >= 500 and attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                    continue

                response.raise_for_status()
                return response
            except (requests.ConnectionError, requests.Timeout) as net_err:
                if attempt == max_retries - 1:
                    raise GitHubError(f"Kegagalan koneksi jaringan ke GitHub: {net_err.__class__.__name__}")
                time.sleep(1.0 * (attempt + 1))
        raise GitHubError("Gagal mengirim permintaan ke GitHub setelah batas pengulangan.")

    def get_repo(self, full_name: str) -> dict[str, Any]:
        """Mengambil data metadata repositori GitHub."""
        return self._request("GET", f"repos/{full_name}").json()

    def get_issue(self, full_name: str, number: int) -> dict[str, Any]:
        """Mengambil data satu issue atau pull request."""
        return self._request("GET", f"repos/{full_name}/issues/{number}").json()

    def list_releases(self, full_name: str) -> list[dict[str, Any]]:
        """Mengambil daftar rilis publik untuk repositori."""
        return self._request("GET", f"repos/{full_name}/releases").json()

    def list_issues(self, full_name: str, since: str | None = None) -> list[dict[str, Any]]:
        """Mengambil daftar issue dan PR yang diperbarui sejak waktu tertentu."""
        params: dict[str, Any] = {"state": "all", "sort": "updated", "direction": "asc"}
        if since:
            params["since"] = since
        return self.paginate(f"repos/{full_name}/issues", params=params)

    def list_issue_comments(self, full_name: str, since: str | None = None) -> list[dict[str, Any]]:
        """Mengambil komentar issue yang dibuat sejak waktu tertentu."""
        params: dict[str, Any] = {"sort": "created", "direction": "asc"}
        if since:
            params["since"] = since
        return self.paginate(f"repos/{full_name}/issues/comments", params=params)

    def list_review_comments(self, full_name: str, since: str | None = None) -> list[dict[str, Any]]:
        """Mengambil komentar review PR yang dibuat sejak waktu tertentu."""
        params: dict[str, Any] = {"sort": "created", "direction": "asc"}
        if since:
            params["since"] = since
        return self.paginate(f"repos/{full_name}/pulls/comments", params=params)

    def search_count(self, query: str) -> int:
        """Mencari jumlah kecocokan issue/PR menggunakan Search API."""
        resp = self._request("GET", "search/issues", params={"q": query, "per_page": 1})
        data = resp.json()
        return int(data.get("total_count", 0))

    def paginate(self, endpoint: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Mengambil seluruh data berhalaman menggunakan header Link."""
        current_params = dict(params or {})
        current_params.setdefault("per_page", 100)
        items: list[dict[str, Any]] = []

        next_url: str | None = f"{self.base_url}/{endpoint.lstrip('/')}"
        while next_url:
            resp = self.session.get(next_url, params=current_params, timeout=30.0)
            self._check_rate_limit(resp)
            if resp.status_code != 200:
                break
            page_data = resp.json()
            if isinstance(page_data, list):
                items.extend(page_data)

            # Setelah halaman pertama, parameter url sudah tertanam di link header
            current_params = {}
            next_url = self._extract_next_link(resp.headers.get("Link"))

        return items

    @staticmethod
    def _extract_next_link(link_header: str | None) -> str | None:
        """Mengekstrak URL rel='next' dari header Link paginasi."""
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        return match.group(1) if match else None
