"""Tests for Gmail config resolution and OAuth gather behavior."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

from timefinder import gmail_messages as gmail


def test_load_gmail_config_oauth_mode(tmp_path):
    path = tmp_path / "gmail_config.json"
    path.write_text(
        json.dumps({"auth": "oauth", "email": "user@example.com", "labels": ["INBOX", "SENT"]}),
        encoding="utf-8",
    )
    with patch("timefinder.google_auth.has_google_token", return_value=True):
        config = gmail.load_gmail_config(str(path))
    assert config["auth"] == "oauth"
    assert config["labels"] == ["INBOX", "SENT"]


def test_load_gmail_config_oauth_without_token_raises(tmp_path):
    path = tmp_path / "gmail_config.json"
    path.write_text(json.dumps({"auth": "oauth", "email": "user@example.com"}), encoding="utf-8")
    with patch("timefinder.google_auth.has_google_token", return_value=False):
        with patch.object(gmail, "has_import_sources", return_value=False):
            try:
                gmail.load_gmail_config(str(path))
                assert False, "expected ValueError"
            except ValueError as exc:
                assert "not configured" in str(exc).lower()


def test_load_gmail_config_oauth_falls_back_to_import(tmp_path):
    path = tmp_path / "gmail_config.json"
    import_dir = tmp_path / "gmail_import"
    import_dir.mkdir()
    (import_dir / "mail.eml").write_text("placeholder", encoding="utf-8")
    path.write_text(
        json.dumps({"auth": "oauth", "import_dir": str(import_dir)}),
        encoding="utf-8",
    )
    with patch("timefinder.google_auth.has_google_token", return_value=False):
        config = gmail.load_gmail_config(str(path))
    assert config["auth"] == "import"


def test_resolve_gmail_gather_config_returns_none_without_config_or_import(tmp_path):
    missing = tmp_path / "missing.json"
    with patch.object(gmail, "DEFAULT_IMPORT_DIR", str(tmp_path / "empty_import")):
        assert gmail.resolve_gmail_gather_config(str(missing)) is None


def test_resolve_gmail_gather_config_uses_import_without_config_file(tmp_path, monkeypatch):
    import_dir = tmp_path / "gmail_import"
    import_dir.mkdir()
    (import_dir / "mail.eml").write_text("placeholder", encoding="utf-8")
    missing = tmp_path / "missing.json"
    monkeypatch.setattr(gmail, "DEFAULT_IMPORT_DIR", str(import_dir))
    config = gmail.resolve_gmail_gather_config(str(missing))
    assert config is not None
    assert config["auth"] == "import"


def test_resolve_gmail_gather_config_skips_oauth_without_token(tmp_path):
    path = tmp_path / "grip_config.json"
    path.write_text(json.dumps({"auth": "oauth", "email": "user@example.com"}), encoding="utf-8")
    with patch("timefinder.google_auth.has_google_token", return_value=False):
        with patch.object(gmail, "has_import_sources", return_value=False):
            assert gmail.resolve_gmail_gather_config(str(path)) is None


def test_load_gmail_config_imap_when_app_password_set(tmp_path):
    path = tmp_path / "gmail_config.json"
    path.write_text(
        json.dumps(
            {
                "email": "user@gmail.com",
                "app_password": "abcd efgh",
                "folders": ["INBOX"],
            }
        ),
        encoding="utf-8",
    )
    config = gmail.load_gmail_config(str(path))
    assert config["auth"] == "imap"


def test_normalize_gmail_api_message():
    msg = {
        "id": "abc123",
        "threadId": "thread1",
        "snippet": "Hello team",
        "internalDate": str(int(datetime(2026, 6, 20, 10, 0, 0).timestamp() * 1000)),
        "payload": {
            "headers": [
                {"name": "From", "value": "Alice <alice@example.com>"},
                {"name": "To", "value": "Bob <bob@example.com>"},
                {"name": "Subject", "value": "RCA follow-up"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gd29ybGQ="},
        },
    }
    normalized = gmail.normalize_gmail_api_message(msg, "INBOX")
    assert normalized["subject"] == "RCA follow-up"
    assert "alice@example.com" in normalized["from"]
    assert normalized["folder"] == "INBOX"


def test_run_gmail_backup_oauth_writes_files(tmp_path):
    mock_service = MagicMock()
    list_response = {"messages": [{"id": "m1"}], "nextPageToken": None}
    mock_service.users.return_value.messages.return_value.list.return_value.execute.return_value = (
        list_response
    )
    full_msg = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "test",
        "internalDate": str(int(datetime(2026, 6, 20, 12, 0, 0).timestamp() * 1000)),
        "payload": {
            "headers": [{"name": "Subject", "value": "Test"}],
            "mimeType": "text/plain",
            "body": {"data": "dGVzdA=="},
        },
    }
    mock_service.users.return_value.messages.return_value.get.return_value.execute.return_value = (
        full_msg
    )

    config = {"auth": "oauth", "labels": ["INBOX"]}
    since = datetime(2026, 6, 19)
    files = gmail.run_gmail_backup_oauth(str(tmp_path), config, since, "2026-06-20", service=mock_service)
    assert len(files) == 1
    payload = json.loads(open(files[0], encoding="utf-8").read())
    assert payload[0]["subject"] == "Test"
