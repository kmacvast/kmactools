"""Tests for thread_harvest.py Slack auth and error handling."""
from __future__ import annotations

import json
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from timefinder import thread_harvest as harvest


def _mock_response(payload: dict, headers: dict | None = None) -> MagicMock:
    body = json.dumps(payload).encode("utf-8")
    response = MagicMock()
    response.read.return_value = body
    response.headers = headers or {}
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=False)
    return response


def test_print_missing_scope_error_includes_needed_and_provided(capsys):
    harvest.print_missing_scope_error(
        "conversations.history",
        {"needed": "channels:history", "provided": "identify"},
    )
    err = capsys.readouterr().err
    assert "missing_scope" in err
    assert "channels:history" in err
    assert "identify" in err
    assert "conversations.history" in err
    assert "slack_channels.json" in err


def test_slack_api_call_exits_on_missing_scope(capsys):
    payload = {
        "ok": False,
        "error": "missing_scope",
        "needed": "channels:history,groups:history",
        "provided": "identify,users:read",
    }

    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        with pytest.raises(SystemExit) as exc_info:
            harvest.slack_api_call("conversations.history", "xoxe.xoxp-test", {"channel": "C1"})

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "missing_scope" in err
    assert "channels:history,groups:history" in err
    assert "identify,users:read" in err


def test_resolve_timefinder_shaped_config(tmp_path, capsys):
    path = tmp_path / "slack_channels.json"
    path.write_text(
        json.dumps(
            {
                "slack_token": "xoxc-browser-token",
                "slack_d_cookie": "xoxd-browser-cookie",
                "channels": {"general": "C1"},
            }
        ),
        encoding="utf-8",
    )

    token, cookie = harvest.resolve_credentials(str(path))
    assert token == "xoxc-browser-token"
    assert cookie == "xoxd-browser-cookie"
    assert "TimeFinder Slack config" in capsys.readouterr().err


def test_resolve_cli_shaped_config(tmp_path, capsys):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps(
            {
                "T1TEAM": {
                    "token": "xoxc-cli-token",
                    "refresh_token": "xoxd-cli-cookie",
                }
            }
        ),
        encoding="utf-8",
    )

    token, cookie = harvest.resolve_credentials(str(path))
    assert token == "xoxc-cli-token"
    assert cookie == "xoxd-cli-cookie"
    assert "Team ID: T1TEAM" in capsys.readouterr().err


def test_resolve_cli_shaped_config_with_team_id(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(
        json.dumps(
            {
                "T_OTHER": {"token": "xoxc-other", "cookie": "xoxd-other"},
                "T_TARGET": {"token": "xoxc-target", "cookie": "xoxd-target"},
            }
        ),
        encoding="utf-8",
    )

    token, cookie = harvest.resolve_credentials(str(path), team_id="T_TARGET")
    assert token == "xoxc-target"
    assert cookie == "xoxd-target"


def test_select_auth_path_precedence():
    assert (
        harvest.select_auth_path(Namespace(credentials="/creds.json", slack_config="/tf.json"))
        == "/creds.json"
    )
    assert (
        harvest.select_auth_path(Namespace(credentials=None, slack_config="/tf.json"))
        == "/tf.json"
    )
    assert (
        harvest.select_auth_path(Namespace(credentials=None, slack_config=None))
        == harvest.DEFAULT_SLACK_CONFIG_PATH
    )


def test_run_harvest_uses_timefinder_config_by_default(tmp_path, capsys):
    config = tmp_path / "slack_channels.json"
    config.write_text(
        json.dumps(
            {
                "slack_token": "xoxc-test-token",
                "slack_d_cookie": "xoxd-test-cookie",
                "channels": {},
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    args = harvest.parse_harvest_args(
        ["--channel", "C1", "--slack-config", str(config), "--output", str(out)]
    )

    history = {
        "ok": True,
        "messages": [
            {"ts": "1.0", "text": "root", "reply_count": 1},
            {"ts": "2.0", "text": "standalone"},
        ],
        "response_metadata": {},
    }
    replies = {
        "ok": True,
        "messages": [
            {"ts": "1.0", "text": "root", "reply_count": 1},
            {"ts": "1.1", "text": "reply", "thread_ts": "1.0"},
        ],
        "response_metadata": {},
    }
    calls: list[str] = []

    def fake_api(method, token, params, cookie=None):
        assert token == "xoxc-test-token"
        assert cookie == "xoxd-test-cookie"
        calls.append(method)
        if method == "conversations.history":
            return history
        if method == "conversations.replies":
            return replies
        raise AssertionError(method)

    with patch.object(harvest, "slack_api_call", side_effect=fake_api):
        assert harvest.run_harvest_thread(args) == 0

    assert calls == ["conversations.history", "conversations.replies"]
    saved = json.loads(out.read_text(encoding="utf-8"))
    assert [m["ts"] for m in saved] == ["1.0", "1.1", "2.0"]
    err = capsys.readouterr().err
    assert "TimeFinder Slack config" in err


def test_run_harvest_warns_when_cookie_is_not_xoxd(tmp_path, capsys):
    creds = tmp_path / "credentials.json"
    creds.write_text(
        json.dumps(
            {
                "T1": {
                    "token": "xoxe.xoxp-test-token",
                    "refresh_token": "xoxe-1-not-a-browser-cookie",
                }
            }
        ),
        encoding="utf-8",
    )
    args = harvest.parse_harvest_args(["--channel", "C1", "--credentials", str(creds)])

    with patch.object(harvest, "slack_api_call", side_effect=SystemExit(1)):
        with pytest.raises(SystemExit):
            harvest.run_harvest_thread(args)

    err = capsys.readouterr().err
    assert "does not look like a browser 'd' cookie" in err
