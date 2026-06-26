"""One-shot Slack channel bootstrap for TimeFinder."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.timefinder_cache/slack_channels.json")

TARGET_CHANNELS = [
    "apple-openldap",
    "orion-378849-macos-houdini",
    "team_fred",
]


def fetch_all_channels(token, d_cookie):
    """Queries the Slack API and paginates to map channel names to IDs."""
    channel_map = {}
    cursor = None
    has_more = True

    print("Connecting to Slack to scan workspace channels...")

    while has_more:
        url = "https://slack.com/api/conversations.list"
        params = {
            "types": "public_channel,private_channel",
            "limit": 1000,
        }
        if cursor:
            params["cursor"] = cursor

        url_with_params = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url_with_params)
        req.add_header("Authorization", f"Bearer {token}")
        if d_cookie:
            req.add_header("Cookie", f"d={d_cookie}")

        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())

                if not data.get("ok"):
                    print(f"Error from Slack API: {data.get('error')}")
                    return None

                for channel in data.get("channels", []):
                    channel_map[channel["name"]] = channel["id"]

                meta = data.get("response_metadata", {})
                cursor = meta.get("next_cursor")
                has_more = bool(cursor)

                if has_more:
                    time.sleep(0.5)

        except Exception as exc:
            print(f"Network error during scan: {exc}")
            return None

    return channel_map


def run_init_channels() -> None:
    """Bootstrap Slack channel config from a fixed target list."""
    print("--- TimeFinder Slack Config Generator ---")
    token = input("Enter your xoxc token: ").strip()
    cookie = input("Enter your d cookie value: ").strip()

    if not token or not cookie:
        print("Error: Both token and cookie are required to authenticate.")
        return

    full_workspace_map = fetch_all_channels(token, cookie)

    if not full_workspace_map:
        print("Failed to look up workspace channels. Configuration not saved.")
        return

    matched_channels = {}
    missing_channels = []

    for name in TARGET_CHANNELS:
        if name in full_workspace_map:
            matched_channels[name] = full_workspace_map[name]
        else:
            missing_channels.append(name)

    config_data = {
        "slack_token": token,
        "slack_d_cookie": cookie,
        "channels": matched_channels,
    }

    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as handle:
            json.dump(config_data, handle, indent=4)
        print(f"\nSuccess: Configuration automatically written to {CONFIG_PATH}")

        print(f"Mapped {len(matched_channels)} channels successfully:")
        for name, cid in matched_channels.items():
            print(f"  {name} -> {cid}")

        if missing_channels:
            print("\nWarning: The following channels were not found or are inaccessible:")
            for name in missing_channels:
                print(f"  {name}")

    except Exception as exc:
        print(f"Failed to write configuration file: {exc}")
