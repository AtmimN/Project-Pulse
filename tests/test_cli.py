"""Pengujian antarmuka baris perintah (CLI)."""
import argparse
from app.cli.__main__ import dispatch_command


def test_cli_dispatch_init_db(capsys) -> None:
    """Menguji eksekusi perintah init-db melalui dispatcher CLI."""
    args = argparse.Namespace(subcommand="init-db")
    dispatch_command(args)
    captured = capsys.readouterr()
    assert "Menginisialisasi basis data" in captured.out
    assert "mode WAL" in captured.out


def test_cli_dispatch_stub_commands(capsys) -> None:
    """Memastikan perintah batch berikutnya menampilkan informasi milestone terkait."""
    commands = [
        ("build-training-data", "Milestone M2"),
        ("train-models", "Milestone M2"),
        ("snapshot-repos", "Milestone M2"),
        ("validate-sentiment", "Milestone M3"),
        ("backtest-alerts", "Milestone M4"),
    ]
    for cmd, milestone in commands:
        args = argparse.Namespace(subcommand=cmd)
        dispatch_command(args)
        captured = capsys.readouterr()
        assert milestone in captured.out
