#!/usr/bin/env python3
################################################################################
# Script Name: vast-opstat.py
# Description: Multi-protocol VAST performance statistics tool. Phase 1 routes
#              --nfs --version=3.0 to the NFS v3 monitor.
#
# Author: KMac kmac@vastdata.com
# Version: 1.0.0
################################################################################

import argparse
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import nfs_v3

VERSION = "1.0.0"

DEFAULT_PORT = 443
DEFAULT_USER = "admin"
DEFAULT_REFRESH_SECONDS = 5

SUPPORTED_NFS_VERSIONS = frozenset({"3.0"})
PLANNED_NFS_VERSIONS = frozenset({"4.1", "4.2"})


def new_argument_parser(description):
    try:
        return argparse.ArgumentParser(description=description, color=False)
    except TypeError:
        return argparse.ArgumentParser(description=description)


def validate_protocol_args(args):
    """Validate protocol flag combinations after argparse parsing."""
    if args.nfs:
        if not args.protocol_version:
            raise SystemExit(
                "ERROR: --version is required when using --nfs.\n"
                "Example: vast-opstat.py --nfs --version=3.0 --vms <VMS_IP>"
            )
        if args.protocol_version in PLANNED_NFS_VERSIONS:
            raise SystemExit(
                f"ERROR: NFS version '{args.protocol_version}' is not implemented yet.\n"
                f"Supported NFS versions: {', '.join(sorted(SUPPORTED_NFS_VERSIONS))}"
            )
        if args.protocol_version not in SUPPORTED_NFS_VERSIONS:
            raise SystemExit(
                f"ERROR: Unsupported NFS version '{args.protocol_version}'.\n"
                f"Supported NFS versions: {', '.join(sorted(SUPPORTED_NFS_VERSIONS))}"
            )
        return

    if args.block:
        if not args.nvme_over_tcp:
            raise SystemExit(
                "ERROR: --block requires --nvme-over-tcp.\n"
                "Example: vast-opstat.py --block --nvme-over-tcp --vms <VMS_IP>"
            )
        raise SystemExit("ERROR: NVMe-oTCP statistics are not implemented yet.")

    if args.smb:
        raise SystemExit("ERROR: SMB statistics are not implemented yet.")


def parse_args(argv=None):
    parser = new_argument_parser(
        "VAST multi-protocol performance statistics (opstat)"
    )

    protocol = parser.add_mutually_exclusive_group(required=True)
    protocol.add_argument(
        "--block",
        action="store_true",
        help="Block storage protocol statistics",
    )
    protocol.add_argument(
        "--nfs",
        action="store_true",
        help="NFS protocol statistics (requires --version)",
    )
    protocol.add_argument(
        "--smb",
        action="store_true",
        help="SMB protocol statistics",
    )

    parser.add_argument(
        "--nvme-over-tcp",
        action="store_true",
        help="Use NVMe-oTCP transport (requires --block)",
    )
    parser.add_argument(
        "--version",
        dest="protocol_version",
        default=None,
        metavar="VER",
        help="Protocol version (required with --nfs, e.g. 3.0)",
    )

    parser.add_argument("--vms", required=True, help="VMS hostname or IP")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"VMS HTTPS port. Default: {DEFAULT_PORT}",
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_USER,
        help=f"VMS username. Default: {DEFAULT_USER}",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="VMS password. If omitted, you will be prompted securely.",
    )
    parser.add_argument(
        "--sample-average",
        default=None,
        help="Optional rolling sample-average window, such as 10m, 1h, or 4h.",
    )
    parser.add_argument(
        "--refresh",
        type=int,
        default=DEFAULT_REFRESH_SECONDS,
        help=f"Refresh interval in seconds. Default: {DEFAULT_REFRESH_SECONDS}",
    )
    parser.add_argument(
        "--csv",
        default=None,
        metavar="FILENAME",
        help="Write captured samples to the specified CSV file.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI color output.",
    )
    parser.add_argument(
        "--discover-metrics",
        action="store_true",
        help="Enumerate NFS metrics and objects available from VMS, then exit.",
    )
    parser.add_argument(
        "-V",
        "--tool-version",
        action="version",
        version=VERSION,
        help="Print vast-opstat version and exit.",
    )

    args = parser.parse_args(argv)
    validate_protocol_args(args)
    return args


def dispatch(args):
    """Route parsed arguments to the appropriate protocol handler."""
    if args.nfs and args.protocol_version == "3.0":
        return nfs_v3.run(args)
    raise SystemExit("ERROR: No protocol handler matched the supplied flags.")


def main(argv=None):
    args = parse_args(argv)
    return dispatch(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
