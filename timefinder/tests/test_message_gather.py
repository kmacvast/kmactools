"""Tests for message_gather.py and message source helpers."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from timefinder import gmail_messages as gmail
from timefinder import message_gather
from timefinder import slack_messages as slack


def _mock_response(payload: dict) -> MagicMock:
    body = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = body
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_resolve_sources_default_includes_slack_and_gmail():
    args = message_gather.parse_gather_args([])
    assert message_gather.resolve_sources(args) == {"slack", "gmail"}


def test_resolve_sources_slack_only():
    args = message_gather.parse_gather_args(["--slack-only"])
    assert message_gather.resolve_sources(args) == {"slack"}


def test_resolve_sources_gmail_only():
    args = message_gather.parse_gather_args(["--gmail-only"])
    assert message_gather.resolve_sources(args) == {"gmail"}


def test_run_gather_messages_runs_both_sources():
    args = message_gather.parse_gather_args([])
    gmail_config = {"auth": "import", "email": "", "import_dir": "/tmp/import"}
    with patch.object(message_gather, "run_slack_backup", return_value=["/tmp/slack.json"]) as slack_mock, patch.object(
        message_gather, "resolve_gmail_gather_config", return_value=gmail_config
    ), patch.object(message_gather, "run_gmail_backup", return_value=["/tmp/gmail.json"]) as gmail_mock:
        assert message_gather.run_gather_messages(args) == 0
    slack_mock.assert_called_once()
    gmail_mock.assert_called_once()


def test_run_gather_messages_skips_gmail_when_unconfigured():
    args = message_gather.parse_gather_args([])
    with patch.object(message_gather, "run_slack_backup", return_value=["/tmp/slack.json"]) as slack_mock, patch.object(
        message_gather, "resolve_gmail_gather_config", return_value=None
    ), patch.object(message_gather, "run_gmail_backup") as gmail_mock:
        assert message_gather.run_gather_messages(args) == 0
    slack_mock.assert_called_once()
    gmail_mock.assert_not_called()


def test_run_gather_messages_fails_when_gmail_errors():
    args = message_gather.parse_gather_args(["--require-gmail"])
    gmail_config = {"auth": "oauth", "email": "user@example.com", "labels": ["INBOX"]}
    with patch.object(message_gather, "run_slack_backup", return_value=["/tmp/slack.json"]), patch.object(
        message_gather, "resolve_gmail_gather_config", return_value=gmail_config
    ), patch.object(
        message_gather,
        "run_gmail_backup",
        side_effect=RuntimeError("Gmail API error"),
    ):
        assert message_gather.run_gather_messages(args) == 1


def test_run_gather_messages_fails_when_require_gmail_and_skipped():
    args = message_gather.parse_gather_args(["--require-gmail"])
    with patch.object(message_gather, "run_slack_backup", return_value=["/tmp/slack.json"]), patch.object(
        message_gather, "resolve_gmail_gather_config", return_value=None
    ):
        assert message_gather.run_gather_messages(args) == 1


def test_run_gather_messages_slack_only_skips_gmail():
    args = message_gather.parse_gather_args(["--slack-only"])
    with patch.object(message_gather, "run_slack_backup", return_value=["/tmp/slack.json"]) as slack_mock, patch.object(
        message_gather, "resolve_gmail_gather_config"
    ) as resolve_mock, patch.object(message_gather, "run_gmail_backup") as gmail_mock:
        assert message_gather.run_gather_messages(args) == 0
    slack_mock.assert_called_once()
    resolve_mock.assert_not_called()
    gmail_mock.assert_not_called()


def test_run_gather_messages_fails_when_slack_errors():
    args = message_gather.parse_gather_args([])
    with patch.object(
        message_gather,
        "run_slack_backup",
        side_effect=FileNotFoundError("Slack configuration not found"),
    ), patch.object(message_gather, "resolve_gmail_gather_config", return_value=None):
        assert message_gather.run_gather_messages(args) == 1


def test_run_gather_messages_mutually_exclusive_flags():
    args = message_gather.parse_gather_args(["--slack-only", "--gmail-only"])
    assert message_gather.run_gather_messages(args) == 1


def test_dedupe_messages_by_ts():
    messages = [
        {"ts": "1.0", "text": "first"},
        {"ts": "1.0", "text": "duplicate"},
        {"ts": "2.0", "text": "second"},
    ]
    deduped = slack.dedupe_messages_by_ts(messages)
    assert len(deduped) == 2
    assert deduped[0]["text"] == "first"


def test_collect_user_ids():
    messages = [{"user": "U1"}, {"user": "U2"}, {"text": "no user"}]
    assert slack.collect_user_ids(messages) == {"U1", "U2"}


def test_enrich_with_thread_replies_merges_replies():
    parent = {"ts": "100.0", "reply_count": 2, "text": "parent"}
    reply = {"ts": "100.1", "thread_ts": "100.0", "text": "reply"}
    replies_response = _mock_response({"ok": True, "messages": [parent, reply]})

    def urlopen_fn(request):
        if "conversations.replies" in request.full_url:
            return replies_response
        raise AssertionError("unexpected request")

    messages = [parent]
    merged, added = slack.enrich_with_thread_replies(
        messages, "token", "cookie", "C123", urlopen_fn=urlopen_fn
    )
    assert added == 1
    assert len(merged) == 2


def test_folder_to_slug():
    assert gmail.folder_to_slug("INBOX") == "inbox"
    assert gmail.folder_to_slug("[Gmail]/Sent Mail") == "sent_mail"


def test_normalize_gmail_message_parses_headers():
    raw = (
        b"From: Alice <alice@example.com>\r\n"
        b"To: Bob <bob@example.com>\r\n"
        b"Subject: Test Subject\r\n"
        b"Date: Mon, 22 Jun 2026 10:00:00 -0600\r\n"
        b"\r\n"
        b"Hello from Gmail."
    )
    normalized = gmail.normalize_gmail_message("1", "INBOX", raw)
    assert normalized["subject"] == "Test Subject"
    assert "alice@example.com" in normalized["from"]
    assert "Hello from Gmail." in normalized["body_excerpt"]
