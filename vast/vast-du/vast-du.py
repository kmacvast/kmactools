#!/usr/bin/env python3
################################################################################
# Script Name:    vast-du.py
# Description:    Queries the VAST Data REST API via the /api/quotas/ endpoint
#                 to retrieve capacity metrics and calculate the Data Reduction
#                 Ratio (DRR) for a specified directory path.
#
# Author:         KMac kmac@vastdata.com
# Version:        0.4.2
################################################################################

import argparse
import sys

from vastpy import VASTClient

from vast.common.utils import load_vast_config


def get_vast_client(config: dict) -> VASTClient:
    """
    Initialize a VASTClient using the provided configuration.

    Args:
        config: Dictionary containing VMS connection details.

    Returns:
        An authenticated VASTClient instance.
    """
    if config.get("token"):
        return VASTClient(
            address=config["vms"],
            token=config["token"],
            tenant=config.get("tenant"),
        )
    return VASTClient(
        address=config["vms"],
        user=config["user"],
        password=config["password"],
        tenant=config.get("tenant"),
    )


def fetch_quota_for_path(client: VASTClient, path: str) -> dict | None:
    """
    Query the /api/quotas/ endpoint for a specific path.

    Args:
        client: An authenticated VASTClient instance.
        path: The VAST logical path to query.

    Returns:
        The quota dictionary for the path, or None if not found.
    """
    # Schema-less pattern: client.quotas.get() → GET /api/quotas/
    quotas = client.quotas.get(path=path.rstrip("/"))

    if not quotas:
        return None

    # Return the first matching quota (exact path match)
    for quota in quotas:
        if quota.get("path", "").rstrip("/") == path.rstrip("/"):
            return quota

    # If no exact match, return first result if available
    return quotas[0] if quotas else None


def calculate_drr(logical_bytes: int, physical_bytes: int) -> float:
    """
    Calculate the Data Reduction Ratio.

    Args:
        logical_bytes: Logical (pre-reduction) capacity in bytes.
        physical_bytes: Physical (post-reduction) capacity in bytes.

    Returns:
        The DRR as a float ratio. Returns 1.0 if physical is zero.
    """
    if physical_bytes <= 0:
        return 1.0
    return logical_bytes / physical_bytes


def bytes_to_gib(value: int) -> float:
    """Convert bytes to GiB."""
    return value / (1024**3)


def format_capacity_table(path: str, logical_gib: float, physical_gib: float, drr: float) -> str:
    """
    Format capacity metrics as a clean ASCII table.

    Args:
        path: The queried path.
        logical_gib: Logical capacity in GiB.
        physical_gib: Physical capacity in GiB.
        drr: Data Reduction Ratio.

    Returns:
        Formatted table string.
    """
    width = 60
    sep = "-" * width

    lines = [
        "",
        sep,
        f"{'VAST Disk Usage Report':<{width}}",
        sep,
        f"{'Path:':<20} {path}",
        sep,
        f"{'Metric':<30} {'Value':>25}",
        sep,
        f"{'Logical Capacity':<30} {logical_gib:>22.2f} GiB",
        f"{'Physical Capacity':<30} {physical_gib:>22.2f} GiB",
        f"{'Data Reduction Ratio (DRR)':<30} {drr:>24.2f}:1",
        sep,
        "",
    ]
    return "\n".join(lines)


def run_vast_du(path: str, config: dict) -> dict:
    """
    Main logic to query VAST and return capacity metrics.

    Args:
        path: The VAST logical path to query.
        config: VAST configuration dictionary.

    Returns:
        Dictionary with path, logical_gib, physical_gib, drr, or error.
    """
    client = get_vast_client(config)
    quota = fetch_quota_for_path(client, path)

    if not quota:
        return {"path": path, "error": f"No quota found for path: {path}"}

    logical_bytes = quota.get("used_capacity", 0)
    physical_bytes = quota.get("used_capacity_tb", 0)

    # Handle different API response field names
    if "used_effective_capacity" in quota:
        logical_bytes = quota["used_effective_capacity"]
    if "used_capacity" in quota and "used_effective_capacity" in quota:
        physical_bytes = quota["used_capacity"]

    drr = calculate_drr(logical_bytes, physical_bytes)

    return {
        "path": path,
        "logical_gib": round(bytes_to_gib(logical_bytes), 2),
        "physical_gib": round(bytes_to_gib(physical_bytes), 2),
        "drr": round(drr, 2),
    }


def main() -> int:
    """
    Entry point for the vast-du CLI tool.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    parser = argparse.ArgumentParser(
        description="VAST Disk Usage - Query capacity metrics and DRR for a path.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  vast-du.py --path /data/projects
  vast-du.py -p /home/users
        """,
    )
    parser.add_argument(
        "-p", "--path",
        required=True,
        help="VAST logical path to query for capacity metrics",
    )
    parser.add_argument(
        "--config",
        default="~/.vastconf",
        help="Path to VAST config file (default: ~/.vastconf)",
    )

    args = parser.parse_args()

    try:
        config = load_vast_config(args.config)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    result = run_vast_du(args.path, config)

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        return 1

    output = format_capacity_table(
        result["path"],
        result["logical_gib"],
        result["physical_gib"],
        result["drr"],
    )
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
