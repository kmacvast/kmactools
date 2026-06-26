"""Gather Slack and Gmail messages for TimeFinder."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from timefinder.gmail_messages import DEFAULT_CONFIG_PATH as GMAIL_CONFIG_PATH
from timefinder.gmail_messages import DEFAULT_OUTPUT_DIR
from timefinder.gmail_messages import run_gmail_backup
from timefinder.slack_messages import DEFAULT_CONFIG_PATH as SLACK_CONFIG_PATH
from timefinder.slack_messages import DEFAULT_USER_MAP_PATH
from timefinder.slack_messages import run_slack_backup

LOG_FILE = "/tmp/timefinder_messages.log"


def parse_gather_args(argv=None):
    """Parse command-line arguments for message gathering."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--slack-config", default=SLACK_CONFIG_PATH)
    parser.add_argument("--gmail-config", default=GMAIL_CONFIG_PATH)
    parser.add_argument("--user-map", default=DEFAULT_USER_MAP_PATH)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(argv)


def configure_logging(verbose: bool) -> None:
    """Configure file logging, with optional console output."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    file_handler = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.addHandler(file_handler)
    if verbose:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(stream_handler)


def resolve_sources(_args) -> set[str]:
    """Resolve message sources to gather. Slack and Gmail are both required."""
    return {"slack", "gmail"}


def run_gather_messages(args) -> int:
    """Gather Slack and Gmail messages. Both sources must succeed."""
    configure_logging(args.verbose)
    sources = resolve_sources(args)

    logging.info("Starting TimeFinder message gather: %s", ", ".join(sorted(sources)))
    print(f"Gathering messages from: {', '.join(sorted(sources))}")

    created_files = []
    errors = []

    if "slack" in sources:
        print("Slack:")
        try:
            created_files.extend(
                run_slack_backup(
                    output_dir=args.output_dir,
                    config_path=args.slack_config,
                    user_map_path=args.user_map,
                    lookback_days=args.lookback_days,
                )
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            errors.append(f"Slack: {exc}")
            print(f"  Slack failed: {exc}")

    if "gmail" in sources:
        print("Gmail:")
        try:
            created_files.extend(
                run_gmail_backup(
                    output_dir=args.output_dir,
                    config_path=args.gmail_config,
                    lookback_days=args.lookback_days,
                )
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            errors.append(f"Gmail: {exc}")
            print(f"  Gmail failed: {exc}")
            print(
                "  Gmail is required. For Google Workspace use OAuth (SETUP_macOS.md Step 4B); "
                "consumer Gmail can use IMAP app password (Step 4A)."
            )

    print("\nSummary of created files:")
    if created_files:
        for file_path in created_files:
            print(f"  {file_path}")
    else:
        print("  No backup files were generated.")

    if errors:
        return 1
    return 0
