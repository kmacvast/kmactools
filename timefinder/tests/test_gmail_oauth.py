"""Tests for Gmail OAuth API backup path."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock

from timefinder import gmail_messages as gmail


def test_load_gmail_config_oauth_mode(tmp_path):
    path = tmp_path / "gmail_config.json"
    path.write_text(
        json.dumps({"auth": "oauth", "email": "user@example.com", "labels": ["INBOX", "SENT"]}),
        encoding="utf-8",
    )
    config = gmail.load_gmail_config(str(path))
    assert config["auth"] == "oauth"
    assert config["labels"] == ["INBOX", "SENT"]


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
