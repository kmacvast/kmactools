"""Slack message fetch helpers for AlibiGen."""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.alibigen_cache/slack_channels.json")
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/.alibigen_cache")
DEFAULT_USER_MAP_PATH = os.path.expanduser("~/.alibigen_cache/slack_users.json")


def slack_api_get(url, params, token, d_cookie, urlopen_fn=urllib.request.urlopen):
    """Perform an authenticated Slack API GET request."""
    url_with_params = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url_with_params)
    req.add_header("Authorization", f"Bearer {token}")
    if d_cookie:
        req.add_header("Cookie", f"d={d_cookie}")
    with urlopen_fn(req) as response:
        return json.loads(response.read().decode())


def load_slack_config(config_path=DEFAULT_CONFIG_PATH):
    """Load tokens, cookies, and channel items from the JSON config file."""
    logging.info("Loading Slack configuration from: %s", config_path)
    if not os.path.exists(config_path):
        msg = f"Slack configuration not found at {config_path}"
        logging.error(msg)
        raise FileNotFoundError(msg)

    with open(config_path, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    token = config.get("slack_token")
    d_cookie = config.get("slack_d_cookie")
    channels = config.get("channels", {})

    if not token:
        raise ValueError("Missing slack_token in configuration.")

    if token.startswith("xoxc-") and (not d_cookie or "PASTE" in d_cookie):
        logging.warning("xoxc token present but d_cookie is missing or placeholder.")

    logging.info("Slack configuration loaded. Mapped %d channels.", len(channels))
    return token, d_cookie, list(channels.items())


def fetch_past_7_days(token, d_cookie, name, channel_id, oldest_timestamp, urlopen_fn=urllib.request.urlopen):
    """Fetch channel history messages since oldest_timestamp."""
    messages = []
    cursor = None
    has_more = True
    page_count = 1

    logging.info("Fetching Slack history for #%s (%s)", name, channel_id)

    while has_more:
        params = {
            "channel": channel_id,
            "oldest": str(oldest_timestamp),
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            data = slack_api_get(
                "https://slack.com/api/conversations.history",
                params,
                token,
                d_cookie,
                urlopen_fn=urlopen_fn,
            )
        except Exception as exc:
            logging.exception("Network failure while backing up #%s", name)
            raise RuntimeError(f"Slack fetch failed for #{name}: {exc}") from exc

        if not data.get("ok"):
            error_msg = data.get("error")
            raise RuntimeError(f"Slack API error for #{name}: {error_msg}")

        batch_messages = data.get("messages", [])
        messages.extend(batch_messages)
        logging.info("Page %d: retrieved %d Slack messages.", page_count, len(batch_messages))

        meta = data.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        has_more = bool(cursor) and data.get("has_more", False)
        if has_more:
            page_count += 1
            time.sleep(0.5)

    return messages


def fetch_thread_replies(token, d_cookie, channel_id, thread_ts, urlopen_fn=urllib.request.urlopen):
    """Fetch all replies for a threaded parent message."""
    replies = []
    cursor = None
    has_more = True

    while has_more:
        params = {"channel": channel_id, "ts": thread_ts, "limit": 200}
        if cursor:
            params["cursor"] = cursor

        data = slack_api_get(
            "https://slack.com/api/conversations.replies",
            params,
            token,
            d_cookie,
            urlopen_fn=urlopen_fn,
        )
        if not data.get("ok"):
            raise RuntimeError(f"Slack replies API error for thread {thread_ts}: {data.get('error')}")

        replies.extend(data.get("messages", []))
        meta = data.get("response_metadata", {})
        cursor = meta.get("next_cursor")
        has_more = bool(cursor) and data.get("has_more", False)
        if has_more:
            time.sleep(0.5)

    return replies


def lookup_user_name(token, d_cookie, user_id, urlopen_fn=urllib.request.urlopen):
    """Resolve a Slack user id to a display name."""
    try:
        data = slack_api_get(
            "https://slack.com/api/users.info",
            {"user": user_id},
            token,
            d_cookie,
            urlopen_fn=urlopen_fn,
        )
    except Exception:
        logging.exception("Failed users.info lookup for %s", user_id)
        return None

    if not data.get("ok"):
        return None

    user_info = data.get("user", {})
    profile = user_info.get("profile", {})
    for candidate in (
        user_info.get("name"),
        profile.get("display_name"),
        profile.get("real_name"),
    ):
        if candidate and candidate.strip():
            return candidate.strip()
    return None


def load_user_map(path=DEFAULT_USER_MAP_PATH):
    """Load existing Slack user id -> name map."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (json.JSONDecodeError, OSError) as exc:
        logging.warning("Could not load user map %s: %s", path, exc)
    return {}


def save_user_map(user_map, path=DEFAULT_USER_MAP_PATH):
    """Persist merged Slack user id -> name map."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(dict(sorted(user_map.items())), handle, indent=4)


def collect_user_ids(messages):
    """Collect unique Slack user ids from message list."""
    return {message.get("user") for message in messages if message.get("user")}


def update_user_map(user_map, token, d_cookie, user_ids, urlopen_fn=urllib.request.urlopen):
    """Fetch and merge display names for user ids not already mapped."""
    updated = 0
    for user_id in sorted(user_ids):
        if user_id in user_map:
            continue
        name = lookup_user_name(token, d_cookie, user_id, urlopen_fn=urlopen_fn)
        if name:
            user_map[user_id] = name
            updated += 1
        time.sleep(0.05)
    return updated


def dedupe_messages_by_ts(messages):
    """Return messages deduplicated by ts, preserving first occurrence order."""
    seen = set()
    deduped = []
    for message in messages:
        ts = message.get("ts")
        if not ts or ts in seen:
            continue
        seen.add(ts)
        deduped.append(message)
    return deduped


def enrich_with_thread_replies(messages, token, d_cookie, channel_id, urlopen_fn=urllib.request.urlopen):
    """Fetch and merge thread replies for parent messages with reply_count > 0."""
    parents = [
        message
        for message in messages
        if int(message.get("reply_count") or 0) > 0 and message.get("ts")
    ]
    if not parents:
        return messages, 0

    merged = list(messages)
    reply_count = 0
    existing_ts = {message.get("ts") for message in merged if message.get("ts")}

    for parent in parents:
        replies = fetch_thread_replies(token, d_cookie, channel_id, parent["ts"], urlopen_fn=urlopen_fn)
        for reply in replies:
            ts = reply.get("ts")
            if ts and ts not in existing_ts:
                merged.append(reply)
                existing_ts.add(ts)
                reply_count += 1
        time.sleep(0.5)

    return merged, reply_count


def run_slack_backup(
    output_dir=DEFAULT_OUTPUT_DIR,
    config_path=DEFAULT_CONFIG_PATH,
    user_map_path=DEFAULT_USER_MAP_PATH,
    lookback_days=7,
    reference_date=None,
    urlopen_fn=urllib.request.urlopen,
):
    """Fetch Slack messages for configured channels and write JSON backup files."""
    token, d_cookie, channels = load_slack_config(config_path)
    if not channels:
        logging.warning("No Slack channels configured.")
        return []

    os.makedirs(output_dir, exist_ok=True)
    user_map = load_user_map(user_map_path)

    now = reference_date or datetime.now()
    oldest_timestamp = int((now - timedelta(days=lookback_days)).timestamp())
    date_str = now.strftime("%Y-%m-%d")
    created_files = []
    all_user_ids = set()

    for name, channel_id in channels:
        logging.info("Backing up Slack channel #%s", name)
        try:
            messages = fetch_past_7_days(
                token, d_cookie, name, channel_id, oldest_timestamp, urlopen_fn=urlopen_fn
            )
        except RuntimeError as exc:
            logging.error("%s", exc)
            print(f"  Slack #{name}: {exc}")
            continue

        reply_added = 0
        if messages:
            messages, reply_added = enrich_with_thread_replies(
                messages, token, d_cookie, channel_id, urlopen_fn=urlopen_fn
            )
            messages = dedupe_messages_by_ts(messages)
            all_user_ids.update(collect_user_ids(messages))

        if not messages:
            print(f"  Slack #{name}: no records parsed.")
            continue

        output_file = os.path.join(output_dir, f"slack_{name}_{date_str}.json")
        with open(output_file, "w", encoding="utf-8") as handle:
            json.dump(messages, handle, indent=4)
        suffix = f" (+{reply_added} replies)" if reply_added else ""
        print(f"  Slack #{name}: saved {len(messages)} entries{suffix}.")
        created_files.append(output_file)

    if all_user_ids:
        updated = update_user_map(user_map, token, d_cookie, all_user_ids, urlopen_fn=urlopen_fn)
        save_user_map(user_map, user_map_path)
        logging.info("Slack user map updated with %d new entries.", updated)

    return created_files
