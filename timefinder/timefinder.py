#!/usr/bin/env python3
"""Unified TimeFinder CLI — work journal automation from Slack and Gmail."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from timefinder.candidates import parse_generate_args, run_generate_candidates
from timefinder.channels_discover import parse_discover_args, run_discover_slack_channels
from timefinder.channels_init import run_init_channels
from timefinder.channels_resolve import run_add_slack_channels
from timefinder.google_auth import run_setup_google_auth
from timefinder.google_calendar import run_sync_google
from timefinder.ics_review import run_ics_review
from timefinder.message_gather import parse_gather_args, run_gather_messages
from timefinder.thread_harvest import parse_harvest_args, run_harvest_thread


def build_parser() -> argparse.ArgumentParser:
    """Build the unified TimeFinder argument parser."""
    parser = argparse.ArgumentParser(
        description="TimeFinder — gather work activity and build a reviewable work journal.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --init-channels
  %(prog)s --add-slack-channels
  %(prog)s --discover-slack-channels --date 2026-06-26 --lookback-days 7
  %(prog)s --gather-candidate-entries
  %(prog)s --generate-candidates --date 2026-06-22
  %(prog)s --harvest-thread --channel C0123456789
  %(prog)s --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics
  %(prog)s --setup-google-auth
  %(prog)s --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.json
        """.strip(),
    )

    parser.add_argument("--init-channels", action="store_true", help="Bootstrap Slack channel config.")
    parser.add_argument(
        "--add-slack-channels",
        action="store_true",
        help="Interactively resolve Slack channels, DMs, and group DMs.",
    )
    parser.add_argument(
        "--discover-slack-channels",
        action="store_true",
        help="Find Slack conversations where you posted in the --date lookback window.",
    )
    parser.add_argument(
        "--gather-candidate-entries",
        action="store_true",
        help="Gather Slack and/or Gmail messages into local cache (Gmail optional).",
    )
    parser.add_argument(
        "--generate-candidates",
        action="store_true",
        help="Generate work-journal calendar candidates from local backups.",
    )
    parser.add_argument(
        "--harvest-thread",
        action="store_true",
        help="Harvest all messages and thread replies from a Slack channel.",
    )
    parser.add_argument(
        "--review-ics",
        metavar="PATH",
        help="Interactively review and edit an ICS work journal file.",
    )
    parser.add_argument(
        "--setup-google-auth",
        action="store_true",
        help="Run Google OAuth2 browser flow and save token.",
    )
    parser.add_argument(
        "--sync-google",
        metavar="PATH",
        help="Sync approved events from JSON or ICS to Google Calendar.",
    )

    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--slack-only", action="store_true", help="Gather Slack messages only.")
    parser.add_argument("--gmail-only", action="store_true", help="Gather Gmail/import messages only.")
    parser.add_argument(
        "--require-gmail",
        action="store_true",
        help="Fail if Gmail is not configured or gather fails.",
    )
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--slack-config", default=None)
    parser.add_argument("--gmail-config", default=None)
    parser.add_argument("--user-map", default=None)
    parser.add_argument("--verbose", action="store_true")

    parser.add_argument("--input-dir", default=None)
    parser.add_argument("--cluster-window-minutes", type=int, default=60)
    parser.add_argument("--min-confidence", type=float, default=0.65)
    parser.add_argument("--min-duration", type=int, default=15)
    parser.add_argument("--max-duration", type=int, default=120)
    parser.add_argument("--date", dest="reference_date", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--no-ics", action="store_true")
    parser.add_argument("--include-trivial-debug", action="store_true")

    parser.add_argument("--channel", "-c", help="Slack channel ID (with --harvest-thread).")
    parser.add_argument(
        "--credentials",
        default=None,
        help="Override Slack CLI credentials.json for --harvest-thread (default: use slack_channels.json).",
    )
    parser.add_argument("--team-id", default=None, help="Slack team ID for --credentials lookup.")
    parser.add_argument("--output", "-o", default=None, help="Harvest output JSON path.")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Dispatch to the selected TimeFinder capability."""
    parser = build_parser()
    args, _unknown = parser.parse_known_args(argv)

    actions = [
        args.init_channels,
        args.add_slack_channels,
        args.discover_slack_channels,
        args.gather_candidate_entries,
        args.generate_candidates,
        args.harvest_thread,
        bool(args.review_ics),
        args.setup_google_auth,
        bool(args.sync_google),
    ]
    if sum(actions) != 1:
        parser.print_help()
        return 1 if sum(actions) > 1 else 0

    if args.init_channels:
        run_init_channels()
        return 0

    if args.add_slack_channels:
        run_add_slack_channels()
        return 0

    if args.discover_slack_channels:
        discover_argv = ["--lookback-days", str(args.lookback_days)]
        if args.reference_date:
            discover_argv.extend(["--date", args.reference_date])
        if args.slack_config:
            discover_argv.extend(["--slack-config", args.slack_config])
        if args.verbose:
            discover_argv.append("--verbose")
        discover_args = parse_discover_args(discover_argv)
        return run_discover_slack_channels(discover_args)

    if args.gather_candidate_entries:
        gather_argv = ["--lookback-days", str(args.lookback_days)]
        if args.slack_only:
            gather_argv.append("--slack-only")
        if args.gmail_only:
            gather_argv.append("--gmail-only")
        if args.require_gmail:
            gather_argv.append("--require-gmail")
        if args.output_dir:
            gather_argv.extend(["--output-dir", args.output_dir])
        if args.slack_config:
            gather_argv.extend(["--slack-config", args.slack_config])
        if args.gmail_config:
            gather_argv.extend(["--gmail-config", args.gmail_config])
        if args.user_map:
            gather_argv.extend(["--user-map", args.user_map])
        if args.verbose:
            gather_argv.append("--verbose")
        gather_args = parse_gather_args(gather_argv)
        return run_gather_messages(gather_args)

    if args.generate_candidates:
        gen_argv = []
        if args.input_dir:
            gen_argv.extend(["--input-dir", args.input_dir])
        if args.output_dir:
            gen_argv.extend(["--output-dir", args.output_dir])
        if args.user_map:
            gen_argv.extend(["--user-map", args.user_map])
        gen_argv.extend(["--lookback-days", str(args.lookback_days)])
        gen_argv.extend(["--cluster-window-minutes", str(args.cluster_window_minutes)])
        gen_argv.extend(["--min-confidence", str(args.min_confidence)])
        gen_argv.extend(["--min-duration", str(args.min_duration)])
        gen_argv.extend(["--max-duration", str(args.max_duration)])
        if args.reference_date:
            gen_argv.extend(["--date", args.reference_date])
        if args.dry_run:
            gen_argv.append("--dry-run")
        if args.verbose:
            gen_argv.append("--verbose")
        if args.debug:
            gen_argv.append("--debug")
        if args.no_ics:
            gen_argv.append("--no-ics")
        if args.include_trivial_debug:
            gen_argv.append("--include-trivial-debug")
        gen_args = parse_generate_args(gen_argv)
        return run_generate_candidates(gen_args)

    if args.harvest_thread:
        if not args.channel:
            print("Error: --harvest-thread requires --channel CHANNEL_ID", file=sys.stderr)
            return 1
        harvest_argv = ["--channel", args.channel]
        # Precedence: --credentials overrides TimeFinder config; else --slack-config / default.
        if args.credentials:
            harvest_argv.extend(["--credentials", args.credentials])
        elif args.slack_config:
            harvest_argv.extend(["--slack-config", args.slack_config])
        if args.team_id:
            harvest_argv.extend(["--team-id", args.team_id])
        if args.output:
            harvest_argv.extend(["--output", args.output])
        harvest_args = parse_harvest_args(harvest_argv)
        return run_harvest_thread(harvest_args)

    if args.review_ics:
        return run_ics_review(args.review_ics)

    if args.setup_google_auth:
        return run_setup_google_auth()

    if args.sync_google:
        return run_sync_google(args.sync_google)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
