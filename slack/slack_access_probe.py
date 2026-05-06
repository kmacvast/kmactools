################################################################################
# Script: slack_access_probe.py
# Descr:  Probe Slack Web API access for the current token and optional channel.
# Date:   2026-04-24
# Author: Kevn
#
# Usage:
#   export SLACK_TOKEN="xoxb-or-xoxp-token-here"
#   python3 slack_access_probe.py
#
#   export SLACK_CHANNEL_ID="C0123456789"
#   python3 slack_access_probe.py
#
# Notes:
#   This script performs read-only Slack API checks.
#   It does not send messages, modify channels, mark messages read, or write data.
#   Prefer testing with an approved Slack app token from your company.
################################################################################

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error


SLACK_TOKEN = os.environ.get("SLACK_TOKEN", "").strip()
SLACK_CHANNEL_ID = os.environ.get("SLACK_CHANNEL_ID", "").strip()


def slack_api(method, payload=None):
    url = f"https://slack.com/api/{method}"
    data = None
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    if payload:
        data = urllib.parse.urlencode(payload).encode("utf-8")

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return {"ok": False, "http_error": exc.code, "body": body}
    except Exception as exc:
        return {"ok": False, "exception": str(exc)}


def result_line(name, response):
    ok = response.get("ok")
    error = response.get("error", "")
    warning = response.get("warning", "")
    if ok:
        status = "OK"
    else:
        status = f"NO: {error or response.get('exception') or response.get('http_error') or 'unknown'}"

    if warning:
        status = f"{status} WARNING: {warning}"

    print(f"{name:<32} {status}")


def print_json(title, value):
    print()
    print(title)
    print(json.dumps(value, indent=2, sort_keys=True))


def main():
    if not SLACK_TOKEN:
        print("Missing SLACK_TOKEN.")
        print('Run: export SLACK_TOKEN="xoxb-or-xoxp-token-here"')
        sys.exit(1)

    print()
    print("Slack Access Probe")
    print("==================")

    auth = slack_api("auth.test")
    result_line("auth.test", auth)

    if auth.get("ok"):
        print(f"Team: {auth.get('team')}")
        print(f"User: {auth.get('user')}")
        print(f"Team ID: {auth.get('team_id')}")
        print(f"User ID: {auth.get('user_id')}")
        print(f"Bot ID: {auth.get('bot_id', 'not a bot token or not returned')}")

    tests = []

    tests.append(("users.info self", "users.info", {"user": auth.get("user_id", "")}))
    tests.append(("conversations.list public", "conversations.list", {"types": "public_channel", "limit": 10}))
    tests.append(("conversations.list private", "conversations.list", {"types": "private_channel", "limit": 10}))
    tests.append(("conversations.list mpim", "conversations.list", {"types": "mpim", "limit": 10}))
    tests.append(("conversations.list im", "conversations.list", {"types": "im", "limit": 10}))

    for label, method, payload in tests:
        response = slack_api(method, payload)
        result_line(label, response)

    if SLACK_CHANNEL_ID:
        print()
        print(f"Channel Probe: {SLACK_CHANNEL_ID}")
        print("==============================")

        channel_tests = [
            ("conversations.info", "conversations.info", {"channel": SLACK_CHANNEL_ID}),
            ("conversations.history", "conversations.history", {"channel": SLACK_CHANNEL_ID, "limit": 5}),
        ]

        history_response = None

        for label, method, payload in channel_tests:
            response = slack_api(method, payload)
            result_line(label, response)
            if method == "conversations.history":
                history_response = response

        if history_response and history_response.get("ok"):
            messages = history_response.get("messages", [])
            threaded = [m for m in messages if m.get("thread_ts") or m.get("reply_count")]

            print(f"Messages visible in latest sample: {len(messages)}")
            print(f"Thread-like messages in sample: {len(threaded)}")

            if threaded:
                thread_ts = threaded[0].get("thread_ts") or threaded[0].get("ts")
                replies = slack_api(
                    "conversations.replies",
                    {"channel": SLACK_CHANNEL_ID, "ts": thread_ts, "limit": 5},
                )
                result_line("conversations.replies", replies)
            else:
                print("conversations.replies         SKIPPED: no thread candidate in latest sample")
    else:
        print()
        print("No SLACK_CHANNEL_ID set, so channel-specific checks were skipped.")
        print('Run: export SLACK_CHANNEL_ID="C0123456789" to test a specific channel.')

    print()
    print("Done.")


if __name__ == "__main__":
    main()