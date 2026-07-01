"""Discover Slack conversations where the authenticated user posted in a date window."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from timefinder.candidates import parse_reference_date, resolve_time_window
from timefinder.slack_messages import DEFAULT_CONFIG_PATH, lookup_user_name, slack_api_get

CONVERSATION_TYPES = "public_channel,private_channel,im,mpim"


@dataclass
class DiscoveredConversation:
    """A Slack conversation with user activity in the scan window."""

    name: str
    channel_id: str
    conv_type: str
    post_count: int
    last_post: datetime | None
    tracked: bool


def parse_discover_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for Slack channel discovery."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--date", dest="reference_date", help="Reference date YYYY-MM-DD")
    parser.add_argument("--slack-config", default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def load_slack_config(config_path: str = DEFAULT_CONFIG_PATH) -> dict:
    """Load the full Slack configuration document."""
    expanded = os.path.expanduser(config_path)
    if not os.path.exists(expanded):
        raise FileNotFoundError(f"Slack configuration not found at {expanded}")

    with open(expanded, "r", encoding="utf-8") as handle:
        config = json.load(handle)
    if not isinstance(config, dict):
        raise ValueError(f"Slack configuration must be a JSON object: {expanded}")
    return config


def save_slack_config(config_path: str, config: dict) -> None:
    """Persist the Slack configuration document."""
    expanded = os.path.expanduser(config_path)
    directory = os.path.dirname(expanded)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(expanded, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=4)
        handle.write("\n")


def load_slack_credentials(config_path: str = DEFAULT_CONFIG_PATH) -> tuple[str, str, dict[str, str]]:
    """Load Slack token, cookie, and any existing tracked channels from config."""
    config = load_slack_config(config_path)

    token = config.get("slack_token")
    d_cookie = config.get("slack_d_cookie")
    channels = config.get("channels") or {}

    if not token:
        raise ValueError("Missing slack_token in Slack configuration.")

    if token.startswith("xoxc-") and (not d_cookie or "PASTE" in d_cookie):
        raise ValueError("xoxc token requires a valid slack_d_cookie in configuration.")

    return token, d_cookie, channels


def fetch_auth_user_id(
    token: str,
    d_cookie: str,
    urlopen_fn=urllib.request.urlopen,
) -> str:
    """Return the authenticated Slack user id from auth.test."""
    data = slack_api_get("https://slack.com/api/auth.test", {}, token, d_cookie, urlopen_fn=urlopen_fn)
    if not data.get("ok"):
        raise RuntimeError(f"Slack auth.test failed: {data.get('error')}")
    user_id = data.get("user_id")
    if not user_id:
        raise RuntimeError("Slack auth.test did not return user_id.")
    return user_id


def list_user_conversations(
    token: str,
    d_cookie: str,
    urlopen_fn=urllib.request.urlopen,
) -> list[dict]:
    """List all conversations visible to the authenticated user."""
    conversations: list[dict] = []
    cursor: str | None = None

    while True:
        params: dict[str, str | int] = {
            "types": CONVERSATION_TYPES,
            "limit": 200,
            "exclude_archived": "true",
        }
        if cursor:
            params["cursor"] = cursor

        data = slack_api_get(
            "https://slack.com/api/users.conversations",
            params,
            token,
            d_cookie,
            urlopen_fn=urlopen_fn,
        )
        if not data.get("ok"):
            raise RuntimeError(f"Slack users.conversations failed: {data.get('error')}")

        conversations.extend(data.get("channels") or [])
        cursor = (data.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.5)

    return conversations


def fetch_history_in_window(
    token: str,
    d_cookie: str,
    channel_id: str,
    oldest_ts: float,
    latest_ts: float,
    urlopen_fn=urllib.request.urlopen,
) -> list[dict]:
    """Fetch channel history messages within a Unix timestamp window."""
    messages: list[dict] = []
    cursor: str | None = None

    while True:
        params: dict[str, str | int] = {
            "channel": channel_id,
            "oldest": str(oldest_ts),
            "latest": str(latest_ts),
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor

        data = slack_api_get(
            "https://slack.com/api/conversations.history",
            params,
            token,
            d_cookie,
            urlopen_fn=urlopen_fn,
        )
        if not data.get("ok"):
            error = data.get("error")
            if error in {"channel_not_found", "not_in_channel", "missing_scope"}:
                logging.debug("Skipping %s: %s", channel_id, error)
                return []
            raise RuntimeError(f"Slack conversations.history failed for {channel_id}: {error}")

        messages.extend(data.get("messages") or [])
        cursor = (data.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
        time.sleep(0.5)

    return messages


def count_user_posts(
    messages: list[dict],
    user_id: str,
    window_start: datetime,
    window_end: datetime,
) -> tuple[int, datetime | None]:
    """Count authenticated-user posts and return the latest post timestamp."""
    post_count = 0
    last_post: datetime | None = None

    for message in messages:
        if message.get("user") != user_id:
            continue
        ts_raw = message.get("ts")
        if not ts_raw:
            continue
        ts = datetime.fromtimestamp(float(ts_raw))
        if ts < window_start or ts > window_end:
            continue
        post_count += 1
        if last_post is None or ts > last_post:
            last_post = ts

    return post_count, last_post


def resolve_conversation_name(
    conversation: dict,
    token: str,
    d_cookie: str,
    user_name_cache: dict[str, str],
    urlopen_fn=urllib.request.urlopen,
) -> tuple[str, str]:
    """Return (display_name, conv_type) for a Slack conversation object."""
    if conversation.get("is_im"):
        peer_id = conversation.get("user", "")
        if peer_id not in user_name_cache:
            user_name_cache[peer_id] = lookup_user_name(token, d_cookie, peer_id, urlopen_fn=urlopen_fn) or peer_id
        return user_name_cache[peer_id], "dm"

    if conversation.get("is_mpim"):
        return conversation.get("name") or f"mpim-{conversation.get('id', 'unknown')}", "mpim"

    return conversation.get("name") or conversation.get("id", "unknown"), "channel"


def is_tracked_conversation(
    name: str,
    channel_id: str,
    tracked_channels: dict[str, str],
    conv_type: str = "channel",
) -> bool:
    """Return True if the conversation is already present in slack_channels.json."""
    if channel_id in tracked_channels.values():
        return True
    key = config_key_for_conversation(name, conv_type)
    return key in tracked_channels or name in tracked_channels


def config_key_for_conversation(name: str, conv_type: str) -> str:
    """Build the slack_channels.json key for a discovered conversation."""
    cleaned = name.strip().lower().lstrip("#@")
    if conv_type == "mpim" and cleaned.startswith("mpdm-"):
        return cleaned
    return cleaned


def merge_untracked_channels(
    config: dict,
    selections: list[DiscoveredConversation],
) -> list[DiscoveredConversation]:
    """Merge selected conversations into config without overwriting existing entries."""
    channels = dict(config.get("channels") or {})
    added: list[DiscoveredConversation] = []

    for item in selections:
        if item.channel_id in channels.values():
            continue

        key = config_key_for_conversation(item.name, item.conv_type)
        if key in channels:
            if channels[key] == item.channel_id:
                continue
            key = f"{key}_{item.channel_id[-4:].lower()}"

        channels[key] = item.channel_id
        added.append(item)

    config["channels"] = dict(sorted(channels.items()))
    return added


def prompt_add_untracked(
    untracked: list[DiscoveredConversation],
    config_path: str,
    config: dict,
    input_fn=input,
) -> list[DiscoveredConversation]:
    """Interactively add untracked discovered conversations to slack_channels.json."""
    print(f"\n{len(untracked)} conversation(s) are not in {config_path}.")
    choice = input_fn(
        "Would you like to add these untracked conversations to your config? "
        "[A]dd All, [S]elect Individually, [C]ancel: "
    ).strip().lower()

    if choice in {"c", "cancel", ""}:
        print("No changes saved.")
        return []

    if choice in {"a", "add", "add all"}:
        selections = list(untracked)
    elif choice in {"s", "select", "select individually"}:
        selections = []
        for item in untracked:
            label = config_key_for_conversation(item.name, item.conv_type)
            answer = input_fn(f"Add '{label}' ({item.channel_id})? [y/n]: ").strip().lower()
            if answer in {"y", "yes"}:
                selections.append(item)
    else:
        print("Unrecognized choice. No changes saved.")
        return []

    if not selections:
        print("No conversations selected. No changes saved.")
        return []

    added = merge_untracked_channels(config, selections)
    if not added:
        print("No new conversations were added.")
        return []

    save_slack_config(config_path, config)
    print(f"Successfully added {len(added)} channel(s) to {config_path}!")
    return added


def discover_active_conversations(
    token: str,
    d_cookie: str,
    user_id: str,
    window_start: datetime,
    window_end: datetime,
    tracked_channels: dict[str, str] | None = None,
    urlopen_fn=urllib.request.urlopen,
) -> list[DiscoveredConversation]:
    """Scan Slack and return conversations where user_id posted in the window."""
    tracked = tracked_channels or {}
    oldest_ts = window_start.timestamp()
    latest_ts = window_end.timestamp()
    user_name_cache: dict[str, str] = {}

    discovered: list[DiscoveredConversation] = []
    conversations = list_user_conversations(token, d_cookie, urlopen_fn=urlopen_fn)

    for index, conversation in enumerate(conversations, start=1):
        channel_id = conversation.get("id")
        if not channel_id:
            continue

        name, conv_type = resolve_conversation_name(
            conversation, token, d_cookie, user_name_cache, urlopen_fn=urlopen_fn
        )
        logging.info("Scanning %s (%s) [%d/%d]", name, channel_id, index, len(conversations))

        messages = fetch_history_in_window(
            token, d_cookie, channel_id, oldest_ts, latest_ts, urlopen_fn=urlopen_fn
        )
        post_count, last_post = count_user_posts(messages, user_id, window_start, window_end)
        if post_count == 0:
            continue

        discovered.append(
            DiscoveredConversation(
                name=name,
                channel_id=channel_id,
                conv_type=conv_type,
                post_count=post_count,
                last_post=last_post,
                tracked=is_tracked_conversation(name, channel_id, tracked, conv_type),
            )
        )
        time.sleep(0.25)

    return sorted(discovered, key=lambda item: (item.last_post or window_start, item.name), reverse=True)


def format_discover_table(discovered: list[DiscoveredConversation]) -> str:
    """Render discovered conversations as a fixed-width ASCII table."""
    if not discovered:
        return "No conversations with your posts were found in the requested window."

    headers = ("Name", "Type", "Slack ID", "Posts", "Last Post", "Tracked")
    rows = [
        (
            item.name,
            item.conv_type,
            item.channel_id,
            str(item.post_count),
            item.last_post.strftime("%Y-%m-%d %H:%M") if item.last_post else "-",
            "yes" if item.tracked else "no",
        )
        for item in discovered
    ]

    widths = [len(header) for header in headers]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]

    def render_row(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(width) for cell, width in zip(cells, widths))

    lines = [render_row(headers), render_row(tuple("-" * width for width in widths))]
    lines.extend(render_row(row) for row in rows)
    return "\n".join(lines)


def run_discover_slack_channels(args: argparse.Namespace) -> int:
    """Discover Slack conversations with user posts in the reference window."""
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        config = load_slack_config(args.slack_config)
        token = config.get("slack_token")
        d_cookie = config.get("slack_d_cookie")
        tracked_channels = config.get("channels") or {}
        if not token:
            raise ValueError("Missing slack_token in Slack configuration.")
        if token.startswith("xoxc-") and (not d_cookie or "PASTE" in d_cookie):
            raise ValueError("xoxc token requires a valid slack_d_cookie in configuration.")
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    reference_date = parse_reference_date(args.reference_date)
    window_start, window_end = resolve_time_window(reference_date, args.lookback_days)

    print(
        f"Discovering Slack conversations with your posts from "
        f"{window_start.date().isoformat()} through {window_end.date().isoformat()}..."
    )

    try:
        user_id = fetch_auth_user_id(token, d_cookie)
        discovered = discover_active_conversations(
            token,
            d_cookie,
            user_id,
            window_start,
            window_end,
            tracked_channels=tracked_channels,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"\nFound {len(discovered)} conversation(s) with your activity:\n")
    print(format_discover_table(discovered))

    untracked = [item for item in discovered if not item.tracked]
    if untracked:
        prompt_add_untracked(untracked, args.slack_config, config)

    return 0
