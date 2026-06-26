"""Harvest all messages and thread replies from a specific Slack channel."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

DEFAULT_CREDS_PATH = os.path.expanduser("~/.slack/credentials.json")


def parse_harvest_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for thread harvest."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--channel", "-c", required=True, help="Slack Channel ID to harvest.")
    parser.add_argument("--credentials", default=DEFAULT_CREDS_PATH)
    parser.add_argument("--team-id", default=None)
    parser.add_argument("--output", "-o", default=None)
    return parser.parse_args(argv)


def print_succinct_setup_instructions() -> None:
    """Print setup instructions for Slack browser credentials."""
    instructions = """
===========================================================================
[-] SLACK AUTHENTICATION FAILED (invalid_auth)
===========================================================================
Your token or session cookie is invalid, missing, or expired.

Follow these succinct steps to refresh your configuration:

1. Open Slack in your desktop web browser and open your Developer Tools:
   * Mac: Cmd + Option + I
   * Windows/Linux: F12

2. Go to the 'Network' tab and type 'client.counts' into the Filter box.
3. Click any channel in your Slack sidebar to trigger network traffic.
4. Click on the 'client.counts' request item that appears and grab:
   * From 'Payload' tab: The 'token' value (starts with xoxc-)
   * From 'Cookies' tab: The value of cookie 'd' (starts with xoxd-)

5. Save these values to your credentials file at:
   ~/.slack/credentials.json

Format Template:
{
  "YOUR_TEAM_ID": {
    "token": "xoxc-YOUR-NEW-BROWSER-TOKEN",
    "refresh_token": "xoxd-YOUR-NEW-COOKIE-STRING",
    "team_domain": "your-org",
    "team_id": "YOUR_TEAM_ID",
    "user_id": "YOUR_USER_ID"
  }
}
===========================================================================
"""
    print(instructions, file=sys.stderr)


def check_token_expiry(team_id: str, team_info: dict[str, Any]) -> None:
    """Check and warn if the token configuration has past its expiration window."""
    exp = team_info.get("exp")
    if exp:
        try:
            exp_time = datetime.fromtimestamp(float(exp))
            if datetime.now() > exp_time:
                print(
                    f"[-] Warning: The token for Team {team_id} expired on "
                    f"{exp_time.strftime('%Y-%m-%d %H:%M:%S')} local time.",
                    file=sys.stderr,
                )
        except (ValueError, OverflowError):
            pass


def resolve_credentials(creds_path: str, team_id: str | None) -> tuple[str | None, str | None]:
    """Extract both the token and the cookie from credentials.json."""
    if not os.path.exists(creds_path):
        print(f"Warning: Credentials file not found at {creds_path}", file=sys.stderr)
        return None, None

    try:
        with open(creds_path, "r", encoding="utf-8") as handle:
            creds_data = json.load(handle)

        if not isinstance(creds_data, dict) or not creds_data:
            print(f"Error: Invalid or empty JSON structure in {creds_path}", file=sys.stderr)
            return None, None

        if team_id:
            team_info = creds_data.get(team_id)
            if team_info and isinstance(team_info, dict):
                check_token_expiry(team_id, team_info)
                cookie = team_info.get("cookie") or team_info.get("refresh_token")
                return team_info.get("token"), cookie
            print(f"Error: Team ID '{team_id}' not found in credentials file.", file=sys.stderr)
            return None, None

        for found_team_id, team_info in creds_data.items():
            if isinstance(team_info, dict) and "token" in team_info:
                check_token_expiry(found_team_id, team_info)
                print(f"[*] Using credentials parsed for Team ID: {found_team_id}", file=sys.stderr)
                cookie = team_info.get("cookie") or team_info.get("refresh_token")
                return team_info["token"], cookie

    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading credentials file {creds_path}: {exc}", file=sys.stderr)

    return None, None


def slack_api_call(
    method: str,
    token: str,
    params: dict[str, Any],
    cookie: str | None = None,
) -> dict[str, Any]:
    """Make a rate-limit aware GET request to the Slack API using urllib."""
    url = f"https://slack.com/api/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")

    if cookie:
        clean_cookie = cookie.strip()
        if clean_cookie.startswith("d="):
            clean_cookie = clean_cookie[2:]
        req.add_header("Cookie", f"d={clean_cookie}")

    max_retries = 5
    for _attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req) as response:
                res = json.loads(response.read().decode("utf-8"))

                if not res.get("ok"):
                    error_code = res.get("error")
                    if error_code == "ratelimited":
                        retry_after = int(response.headers.get("Retry-After", 3))
                        print(f"Rate limited by Slack. Sleeping for {retry_after}s...", file=sys.stderr)
                        time.sleep(retry_after)
                        continue
                    if error_code == "token_expired":
                        print("\n[-] Error: Slack API reports that your token is expired.", file=sys.stderr)
                        print_succinct_setup_instructions()
                        sys.exit(1)
                    if error_code == "invalid_auth":
                        print_succinct_setup_instructions()
                        sys.exit(1)
                    raise RuntimeError(f"Slack API Error [{method}]: {error_code}")
                return res

        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                retry_after = int(exc.headers.get("Retry-After", 5))
                print(f"Rate limited (429). Sleeping for {retry_after}s...", file=sys.stderr)
                time.sleep(retry_after)
                continue
            raise exc

    raise RuntimeError(f"Failed to complete Slack API call to {method} after maximum retries.")


def run_harvest_thread(args: argparse.Namespace) -> int:
    """Harvest channel messages and thread replies to JSON."""
    token, cookie = resolve_credentials(args.credentials, args.team_id)
    if not token:
        print(f"Error: Could not find a valid Slack token inside {args.credentials}", file=sys.stderr)
        print_succinct_setup_instructions()
        return 1

    t_disp = f"{token[:15]}..." if token else "None"
    c_disp = f"{cookie[:15]}..." if cookie else "None"
    print(f"[*] Loaded Token: {t_disp}", file=sys.stderr)
    print(f"[*] Loaded Cookie: {c_disp}", file=sys.stderr)

    channel_id = args.channel
    output_path = args.output or os.path.expanduser(f"~/Downloads/slack_{channel_id}.json")

    messages_map: dict[str, dict[str, Any]] = {}

    print(f"[*] Fetching history for channel {channel_id}...", flush=True)
    cursor = None
    while True:
        params: dict[str, Any] = {"channel": channel_id, "limit": 100}
        if cursor:
            params["cursor"] = cursor

        res = slack_api_call("conversations.history", token, params, cookie=cookie)
        messages = res.get("messages", [])

        for msg in messages:
            messages_map[msg["ts"]] = msg

        print(f"    Loaded {len(messages)} messages (Total unique: {len(messages_map)})", flush=True)

        cursor = res.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break

    thread_roots = [ts for ts, msg in messages_map.items() if msg.get("reply_count", 0) > 0]

    if thread_roots:
        print(f"[*] Found {len(thread_roots)} threads to harvest recursively...", flush=True)
    else:
        print("[*] No threaded replies found in this channel window.", flush=True)

    for idx, root_ts in enumerate(thread_roots, start=1):
        print(f"    [{idx}/{len(thread_roots)}] Fetching replies for thread root {root_ts}...", flush=True)
        cursor = None
        while True:
            params = {"channel": channel_id, "ts": root_ts, "limit": 100}
            if cursor:
                params["cursor"] = cursor

            res = slack_api_call("conversations.replies", token, params, cookie=cookie)
            replies = res.get("messages", [])

            for reply in replies:
                messages_map[reply["ts"]] = reply

            cursor = res.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

    final_list = sorted(messages_map.values(), key=lambda item: float(item["ts"]))

    print(f"[*] Writing {len(final_list)} total messages to {output_path}...", flush=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(final_list, handle, indent=2)
        handle.write("\n")

    print("[+] Done!")
    return 0
