"""Tests for channels_discover.py."""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

from timefinder import channels_discover as discover
from timefinder.tests.conftest import ts_at


def test_count_user_posts_filters_window_and_user():
    window_start = datetime(2026, 6, 19, 0, 0, 0)
    window_end = datetime(2026, 6, 26, 23, 59, 59)
    messages = [
        {"user": "U1", "ts": ts_at(2026, 6, 20, 10)},
        {"user": "U2", "ts": ts_at(2026, 6, 21, 10)},
        {"user": "U1", "ts": ts_at(2026, 6, 29, 10)},
        {"user": "U1", "ts": ts_at(2026, 6, 18, 10)},
    ]
    count, last_post = discover.count_user_posts(messages, "U1", window_start, window_end)
    assert count == 1
    assert last_post == datetime.fromtimestamp(float(ts_at(2026, 6, 20, 10)))


def test_is_tracked_conversation_by_name_or_id():
    tracked = {"apple-openldap": "C111", "seb": "D222"}
    assert discover.is_tracked_conversation("apple-openldap", "C999", tracked)
    assert discover.is_tracked_conversation("unknown", "D222", tracked, "dm")
    assert not discover.is_tracked_conversation("unknown", "C999", tracked)


def test_merge_untracked_channels_preserves_existing(tmp_path):
    config = {
        "slack_token": "xoxc-test",
        "slack_d_cookie": "d-test",
        "channels": {"existing": "C1"},
    }
    selections = [
        discover.DiscoveredConversation(
            name="New-Channel",
            channel_id="C2",
            conv_type="channel",
            post_count=1,
            last_post=None,
            tracked=False,
        ),
        discover.DiscoveredConversation(
            name="Seb",
            channel_id="D9",
            conv_type="dm",
            post_count=1,
            last_post=None,
            tracked=False,
        ),
    ]
    added = discover.merge_untracked_channels(config, selections)
    assert len(added) == 2
    assert config["channels"]["existing"] == "C1"
    assert config["channels"]["new-channel"] == "C2"
    assert config["channels"]["seb"] == "D9"


def test_prompt_add_untracked_add_all(tmp_path):
    config_path = tmp_path / "slack_channels.json"
    config = {"slack_token": "xoxc-test", "slack_d_cookie": "d-test", "channels": {}}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    untracked = [
        discover.DiscoveredConversation(
            name="new-channel",
            channel_id="C2",
            conv_type="channel",
            post_count=1,
            last_post=None,
            tracked=False,
        )
    ]

    added = discover.prompt_add_untracked(
        untracked,
        str(config_path),
        config,
        input_fn=lambda _prompt: "a",
    )
    assert len(added) == 1
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["channels"]["new-channel"] == "C2"
    assert saved["slack_token"] == "xoxc-test"


def test_prompt_add_untracked_select_individually(tmp_path):
    config_path = tmp_path / "slack_channels.json"
    config = {"slack_token": "xoxc-test", "slack_d_cookie": "d-test", "channels": {"keep": "C1"}}
    config_path.write_text(json.dumps(config), encoding="utf-8")
    untracked = [
        discover.DiscoveredConversation(
            name="alpha",
            channel_id="C2",
            conv_type="channel",
            post_count=1,
            last_post=None,
            tracked=False,
        ),
        discover.DiscoveredConversation(
            name="beta",
            channel_id="C3",
            conv_type="channel",
            post_count=1,
            last_post=None,
            tracked=False,
        ),
    ]
    answers = iter(["s", "y", "n"])

    added = discover.prompt_add_untracked(
        untracked,
        str(config_path),
        config,
        input_fn=lambda _prompt: next(answers),
    )
    assert len(added) == 1
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["channels"]["keep"] == "C1"
    assert saved["channels"]["alpha"] == "C2"
    assert "beta" not in saved["channels"]


def test_discover_active_conversations_returns_only_user_posted(tmp_path):
    window_start = datetime(2026, 6, 19, 0, 0, 0)
    window_end = datetime(2026, 6, 26, 23, 59, 59)

    conversations = [
        {"id": "C1", "name": "tracked-channel"},
        {"id": "C2", "name": "new-channel"},
        {"id": "D1", "is_im": True, "user": "UPEER"},
    ]

    history_by_channel = {
        "C1": [{"user": "U1", "ts": ts_at(2026, 6, 20, 9)}],
        "C2": [{"user": "U1", "ts": ts_at(2026, 6, 22, 11)}, {"user": "U2", "ts": ts_at(2026, 6, 22, 12)}],
        "D1": [],
    }

    with patch.object(discover, "list_user_conversations", return_value=conversations), patch.object(
        discover, "fetch_history_in_window", side_effect=lambda _t, _d, cid, *_a, **_k: history_by_channel.get(cid, [])
    ), patch.object(
        discover,
        "resolve_conversation_name",
        side_effect=lambda conv, *_a, **_k: (
            ("peer-name", "dm") if conv.get("is_im") else (conv["name"], "channel")
        ),
    ):
        results = discover.discover_active_conversations(
            "token",
            "cookie",
            "U1",
            window_start,
            window_end,
            tracked_channels={"tracked-channel": "C1"},
        )

    assert len(results) == 2
    by_id = {item.channel_id: item for item in results}
    assert by_id["C1"].tracked is True
    assert by_id["C2"].tracked is False
    assert by_id["C2"].post_count == 1


def test_run_discover_slack_channels_prints_results(tmp_path, capsys):
    config_path = tmp_path / "slack_channels.json"
    config_path.write_text(
        json.dumps({"slack_token": "xoxc-test", "slack_d_cookie": "d-test", "channels": {}}),
        encoding="utf-8",
    )
    args = discover.parse_discover_args(
        ["--date", "2026-06-26", "--lookback-days", "7", "--slack-config", str(config_path)]
    )
    sample = [
        discover.DiscoveredConversation(
            name="new-channel",
            channel_id="C2",
            conv_type="channel",
            post_count=2,
            last_post=datetime(2026, 6, 22, 11, 0, 0),
            tracked=False,
        )
    ]

    with patch.object(discover, "fetch_auth_user_id", return_value="U1"), patch.object(
        discover, "discover_active_conversations", return_value=sample
    ), patch.object(discover, "prompt_add_untracked") as prompt_mock:
        assert discover.run_discover_slack_channels(args) == 0

    captured = capsys.readouterr()
    assert "2026-06-19 through 2026-06-26" in captured.out
    assert "new-channel" in captured.out
    prompt_mock.assert_called_once()
