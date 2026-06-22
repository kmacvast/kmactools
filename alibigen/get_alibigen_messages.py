#!/usr/bin/env python3
"""Gather Slack and Gmail messages for AlibiGen.

Usage:
  ./get_alibigen_messages.py
  ./get_alibigen_messages.py --slack
  ./get_alibigen_messages.py --gmail
  ./get_alibigen_messages.py --lookback-days 7 --verbose

By default fetches both Slack and Gmail. Use --slack or --gmail to limit sources.

Slack config: ~/.alibigen_cache/slack_channels.json
Gmail config: ~/.alibigen_cache/gmail_config.json
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alibigen.gmail_messages import DEFAULT_CONFIG_PATH as GMAIL_CONFIG_PATH
from alibigen.gmail_messages import DEFAULT_OUTPUT_DIR
from alibigen.gmail_messages import run_gmail_backup
from alibigen.slack_messages import DEFAULT_CONFIG_PATH as SLACK_CONFIG_PATH
from alibigen.slack_messages import DEFAULT_USER_MAP_PATH
from alibigen.slack_messages import run_slack_backup

LOG_FILE = "/tmp/get_alibigen_messages.log"


def parse_args(argv=None):
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Gather Slack and Gmail messages for AlibiGen.")
    parser.add_argument("--slack", action="store_true", help="Gather Slack messages only.")
    parser.add_argument("--gmail", action="store_true", help="Gather Gmail messages only.")
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


def resolve_sources(args) -> set[str]:
    """Resolve which message sources to gather."""
    if args.slack or args.gmail:
        sources = set()
        if args.slack:
            sources.add("slack")
        if args.gmail:
            sources.add("gmail")
        return sources
    return {"slack", "gmail"}


def main(argv=None) -> int:
    """Gather Slack and/or Gmail messages."""
    args = parse_args(argv)
    configure_logging(args.verbose)
    sources = resolve_sources(args)

    logging.info("Starting AlibiGen message gather: %s", ", ".join(sorted(sources)))
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
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"Slack: {exc}")
            print(f"  Slack skipped: {exc}")

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
        except (FileNotFoundError, ValueError) as exc:
            errors.append(f"Gmail: {exc}")
            print(f"  Gmail skipped: {exc}")

    print("\nSummary of created files:")
    if created_files:
        for file_path in created_files:
            print(f"  {file_path}")
    else:
        print("  No backup files were generated.")

    if errors and not created_files:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
