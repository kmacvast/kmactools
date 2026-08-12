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

DEFAULT_SLACK_CONFIG_PATH = os.path.expanduser("~/.timefinder_cache/slack_channels.json")
DEFAULT_CREDS_PATH = os.path.expanduser("~/.slack/credentials.json")


def parse_harvest_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for thread harvest."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--channel", "-c", required=True, help="Slack Channel ID to harvest.")
    parser.add_argument(
        "--slack-config",
        default=None,
        help="TimeFinder Slack config path (default: ~/.timefinder_cache/slack_channels.json).",
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="Override: Slack CLI credentials.json path (team-map format).",
    )
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

5. Save these values to ~/.timefinder_cache/slack_channels.json:

{
  "slack_token": "xoxc-YOUR-NEW-BROWSER-TOKEN",
  "slack_d_cookie": "xoxd-YOUR-NEW-COOKIE-STRING",
  "channels": {}
}

Or, for Slack CLI team-map format via --credentials ~/.slack/credentials.json:
{
  "YOUR_TEAM_ID": {
    "token": "xoxc-YOUR-NEW-BROWSER-TOKEN",
    "refresh_token": "xoxd-YOUR-NEW-COOKIE-STRING"
  }
}
===========================================================================
"""
    print(instructions, file=sys.stderr)


def print_missing_scope_error(method: str, response: dict[str, Any]) -> None:
    """Print a clear explanation when Slack rejects a call for missing OAuth scopes."""
    needed = response.get("needed") or "(not reported by Slack)"
    provided = response.get("provided") or "(not reported by Slack)"
    instructions = f"""
===========================================================================
[-] SLACK API PERMISSION ERROR (missing_scope)
===========================================================================
Method:   {method}
Needed:   {needed}
Provided: {provided}

Your Slack token authenticated, but it does not have permission to read
channel history. conversations.history / conversations.replies require one
or more of: channels:history, groups:history, im:history, mpim:history.

Common causes:
  * A Slack CLI login token (xoxe.xoxp-...) was used; those lack *:history.
  * slack_token in ~/.timefinder_cache/slack_channels.json is a service/app
    token without history scopes, or slack_d_cookie is missing for xoxc-.

How to fix (--harvest-thread):
  1. Use the same browser session credentials as gather/discover:
     Open Slack in a browser → DevTools → Network → filter 'client.counts'
     → copy token (xoxc-) and cookie 'd' (xoxd-).
  2. Save them in ~/.timefinder_cache/slack_channels.json as:
       "slack_token": "xoxc-...",
       "slack_d_cookie": "xoxd-..."
  3. Or pass a CLI-format file with xoxc- + xoxd- via --credentials.

Default auth file: ~/.timefinder_cache/slack_channels.json
(same as gather/discover). Override with --slack-config or --credentials.
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


def resolve_timefinder_credentials(config_path: str) -> tuple[str | None, str | None]:
    """Load slack_token and slack_d_cookie from TimeFinder slack_channels.json."""
    if not os.path.exists(config_path):
        print(f"Warning: Slack config not found at {config_path}", file=sys.stderr)
        return None, None

    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = json.load(handle)

        if not isinstance(config, dict) or not config:
            print(f"Error: Invalid or empty JSON structure in {config_path}", file=sys.stderr)
            return None, None

        token = config.get("slack_token")
        if not token:
            print(f"Error: Missing slack_token in {config_path}", file=sys.stderr)
            return None, None

        cookie = config.get("slack_d_cookie") or None
        print(f"[*] Using TimeFinder Slack config: {config_path}", file=sys.stderr)
        return token, cookie

    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading Slack config {config_path}: {exc}", file=sys.stderr)

    return None, None


def resolve_cli_credentials(creds_path: str, team_id: str | None) -> tuple[str | None, str | None]:
    """Extract token and cookie from Slack CLI team-map credentials.json."""
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


def resolve_credentials(
    creds_path: str,
    team_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve token and cookie from TimeFinder or Slack CLI credential file shapes.

    TimeFinder shape: top-level ``slack_token`` / ``slack_d_cookie``.
    Slack CLI shape: team-id map with ``token`` and ``cookie`` / ``refresh_token``.
    """
    if not os.path.exists(creds_path):
        print(f"Warning: Credentials file not found at {creds_path}", file=sys.stderr)
        return None, None

    try:
        with open(creds_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error reading credentials file {creds_path}: {exc}", file=sys.stderr)
        return None, None

    if not isinstance(data, dict) or not data:
        print(f"Error: Invalid or empty JSON structure in {creds_path}", file=sys.stderr)
        return None, None

    if "slack_token" in data:
        return resolve_timefinder_credentials(creds_path)

    return resolve_cli_credentials(creds_path, team_id)


def select_auth_path(args: argparse.Namespace) -> str:
    """Choose auth file path: --credentials wins, else --slack-config, else default."""
    if getattr(args, "credentials", None):
        return args.credentials
    if getattr(args, "slack_config", None):
        return args.slack_config
    return DEFAULT_SLACK_CONFIG_PATH


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
                    if error_code == "missing_scope":
                        print_missing_scope_error(method, res)
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
    auth_path = select_auth_path(args)
    token, cookie = resolve_credentials(auth_path, args.team_id)
    if not token:
        print(f"Error: Could not find a valid Slack token inside {auth_path}", file=sys.stderr)
        print_succinct_setup_instructions()
        return 1

    t_disp = f"{token[:15]}..." if token else "None"
    c_disp = f"{cookie[:15]}..." if cookie else "None"
    print(f"[*] Loaded Token: {t_disp}", file=sys.stderr)
    print(f"[*] Loaded Cookie: {c_disp}", file=sys.stderr)

    if cookie:
        cookie_body = cookie.strip()
        if cookie_body.startswith("d="):
            cookie_body = cookie_body[2:]
        if not cookie_body.startswith("xoxd-"):
            print(
                "[-] Warning: Cookie/refresh_token does not look like a browser 'd' cookie "
                "(expected xoxd-...). Slack CLI refresh tokens often lack history scopes "
                "and will fail conversations.history with missing_scope.",
                file=sys.stderr,
            )
    elif token.startswith("xoxc-"):
        print(
            "[-] Warning: xoxc browser token loaded without an xoxd- cookie; "
            "conversations.history usually fails without both.",
            file=sys.stderr,
        )

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
