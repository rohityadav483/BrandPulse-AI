import logging

from app.db.session import check_database, normalize_url


def test_normalize_url_targets_psycopg3():
    assert normalize_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql+psycopg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("sqlite://") == "sqlite://"


def test_empty_url_is_unavailable():
    assert check_database("") is False


def test_reachable_database_is_ok():
    assert check_database("sqlite://") is True  # stdlib SQLite stands in for a live DB


def test_unreachable_postgres_is_false_and_never_logs_password(caplog):
    url = "postgresql://user:SuperSecretPw@127.0.0.1:1/db"  # port 1: connection refused
    with caplog.at_level(logging.WARNING):
        assert check_database(url) is False
    assert "SuperSecretPw" not in caplog.text
    assert any(r.message == "database_check_failed" for r in caplog.records)
