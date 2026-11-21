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


def test_cli_dispatch_m2_commands(capsys) -> None:
    """Menguji pemanggilan perintah M2 (train-models) via CLI."""
    args = argparse.Namespace(subcommand="train-models")
    dispatch_command(args)
    captured = capsys.readouterr()
    assert "Melatih model regresi" in captured.out


def test_cli_dispatch_m3_commands(capsys) -> None:
    """Menguji pemanggilan perintah M3 (export-label-sample, validate-sentiment, rescore) via CLI."""
    # export-label-sample
    args_export = argparse.Namespace(subcommand="export-label-sample", n=5)
    dispatch_command(args_export)
    captured = capsys.readouterr()
    assert "Mengekspor" in captured.out

    # validate-sentiment
    args_val = argparse.Namespace(subcommand="validate-sentiment")
    dispatch_command(args_val)
    captured = capsys.readouterr()
    assert "Memvalidasi model sentimen" in captured.out

    # rescore
    args_resc = argparse.Namespace(subcommand="rescore")
    dispatch_command(args_resc)
    captured = capsys.readouterr()
    assert "Menghitung ulang sentimen" in captured.out


def test_cli_dispatch_stub_commands(capsys) -> None:
    """Memastikan perintah batch berikutnya menampilkan informasi milestone terkait."""
    commands = [
        ("backtest-alerts", "Milestone M4"),
    ]
    for cmd, milestone in commands:
        args = argparse.Namespace(subcommand=cmd)
        dispatch_command(args)
        captured = capsys.readouterr()
        assert milestone in captured.out
