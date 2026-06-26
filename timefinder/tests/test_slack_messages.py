"""Tests for slack_messages.py."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from timefinder import slack_messages as slack


def _mock_response(payload: dict) -> MagicMock:
    body = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = body
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_load_and_save_user_map(tmp_path):
    path = tmp_path / "slack_users.json"
    slack.save_user_map({"U1": "alice"}, path)
    loaded = slack.load_user_map(path)
    assert loaded == {"U1": "alice"}


def test_lookup_user_name():
    response = _mock_response(
        {
            "ok": True,
            "user": {
                "name": "kmac",
                "profile": {"display_name": "KMac", "real_name": "Kevin MacDonald"},
            },
        }
    )

    def urlopen_fn(_request):
        return response

    assert slack.lookup_user_name("token", "cookie", "U111", urlopen_fn=urlopen_fn) == "kmac"


def test_update_user_map_skips_existing(tmp_path):
    path = tmp_path / "users.json"
    user_map = {"U1": "existing"}

    def urlopen_fn(_request):
        return _mock_response({"ok": True, "user": {"name": "new"}})

    updated = slack.update_user_map(user_map, "token", "cookie", {"U1", "U2"}, urlopen_fn=urlopen_fn)
    assert updated == 1
    assert user_map["U1"] == "existing"
    assert user_map["U2"] == "new"


def test_fetch_thread_replies_paginates():
    page1 = _mock_response(
        {
            "ok": True,
            "messages": [{"ts": "1.0", "text": "a"}],
            "response_metadata": {"next_cursor": "abc"},
            "has_more": True,
        }
    )
    page2 = _mock_response(
        {
            "ok": True,
            "messages": [{"ts": "2.0", "text": "b"}],
            "response_metadata": {"next_cursor": ""},
            "has_more": False,
        }
    )
    calls = {"count": 0}

    def urlopen_fn(_request):
        calls["count"] += 1
        return page1 if calls["count"] == 1 else page2

    replies = slack.fetch_thread_replies("token", "cookie", "C1", "100.0", urlopen_fn=urlopen_fn)
    assert len(replies) == 2
    assert calls["count"] == 2
