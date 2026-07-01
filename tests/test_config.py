"""Tests for DB password resolution in config loading."""

import pytest

from app.config import _db_conninfo

DB_VARS = ("METADATA_API_DB_URL", "DB_PASSWORD_FILE", "DB_PASSWORD")


@pytest.fixture(autouse=True)
def _clear_db_env(monkeypatch):
    for var in DB_VARS:
        monkeypatch.delenv(var, raising=False)


def test_password_read_from_file_is_trimmed(monkeypatch, tmp_path):
    secret = tmp_path / "db_password"
    secret.write_text("  s3cret\n\n")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))

    assert "password=s3cret" in _db_conninfo()


def test_password_file_takes_precedence_over_env(monkeypatch, tmp_path):
    secret = tmp_path / "db_password"
    secret.write_text("from-file")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(secret))
    monkeypatch.setenv("DB_PASSWORD", "from-env")

    assert "password=from-file" in _db_conninfo()


def test_password_defaults_when_nothing_set():
    assert "password=postgres" in _db_conninfo()
