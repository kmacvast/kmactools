#!/usr/bin/env python3
#!/usr/bin/env python3
# ==============================================================================
# SCRIPT NAME : vast_search.py
# DESCRIPTION : High-velocity database pushdown search client leveraging the
#               VAST Data Catalog relational engine. Enables multi-dimensional
#               POSIX, space-efficiency, and rolling chrono-aging filtering
#               across multi-million file sandbox arrays in milliseconds.
#
# AUTHOR      : Kevin McDonald (KMac)
# DATE        : June 23, 2026
# VERSION     : 2.5.0
# LICENSE     : MIT / Enterprise Internal
#
# DEPENDENCIES: python3, pandas, vastdb, ibis-framework
# CONFIG PROFILE: ~/.vast-catalog-config.json
# ==============================================================================
# REVISION HISTORY:
# Date       | Version | Author         | Summary of Changes
# -----------+---------+----------------+---------------------------------------
# 2026-06-23 | 2.5.0   | KMac & Sheila  | Added full POSIX IDs, block metrics,
#            |         |                | and rolling time-aging query flags.
# 2026-06-23 | 2.1.0   | KMac & Sheila  | Patched 403 Forbidden exception
#            |         |                | handlers and bypassed limit for '--limit 0'.
# 2026-06-23 | 1.0.0   | KMac & Sheila  | Initial deployment of baseline search.
# ==============================================================================
# USAGE EXAMPLES:
#   ./vast_search.py --ext JPEG --limit 0 > /tmp/jpeg_images.txt
#   ./vast_search.py --min-size 10M --mmin 30 --limit 20
# ==============================================================================

import os
import sys
import json
import argparse
import time
import re
from datetime import datetime, timedelta
import pandas as pd
import vastdb
from ibis import _

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def load_config():
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        print(f"\n[!] Configuration Error: Local file missing at {DEFAULT_CONFIG_PATH}")
        sys.exit(1)
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            print(f"\n[!] Configuration Error: File at {DEFAULT_CONFIG_PATH} is corrupted.\n")
            sys.exit(1)

def format_bytes(size_bytes: float) -> str:
    if size_bytes == 0: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def parse_human_size(size_str: str) -> int:
    if not size_str: return 0
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KkMmGgTt]?)[Bb]?$", size_str.strip())
    if not match:
        raise ValueError(f"Invalid size layout format: {size_str}")
    value, unit = match.groups()
    value = float(value)
    scale = {'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4, '': 1}[unit.lower()]
    return int(value * scale)

def search_catalog(args):
    config = load_config()
    base_path = "/kmacs/vast-catalog"
    predicate = _.parent_path.startswith(base_path)

    # 1. Base Filters
    if args.name: predicate = predicate & _.name.contains(args.name)
    if args.ext: predicate = predicate & (_.extension == args.ext.lstrip('.'))
    if args.type: predicate = predicate & (_.element_type == args.type.upper())

    # 2. Identity & POSIX Security Filters
    if args.user: predicate = predicate & (_.owner_name == args.user)
    if args.group: predicate = predicate & (_.group_name == args.group)
    if args.uid is not None: predicate = predicate & (_.uid == args.uid)
    if args.gid is not None: predicate = predicate & (_.gid == args.gid)
    if args.mode:
        # Convert octal string notation (e.g. '755') safely to base-10 int match
        dec_mode = int(args.mode, 8) if args.mode.startswith('0') or len(args.mode) == 3 else int(args.mode)
        predicate = predicate & (_.nfs_mode_bits == dec_mode)

    # 3. Capacity, Allocation & Efficiency Filters
    if args.min_size:
        predicate = predicate & (_.size >= parse_human_size(args.min_size))
    if args.min_physical:
        predicate = predicate & (_.used >= parse_human_size(args.min_physical))
    if args.sparse:
        predicate = predicate & (_.size > _.used)

    # 4. Rolling Time-Aging Chrono Filters (Nanosecond Conversions)
    now_ns = int(datetime.now().timestamp() * 1e9)
    if args.mmin:
        predicate = predicate & (_.mtime >= (now_ns - (int(args.mmin) * 60 * 1e9)))
    if args.amin:
        predicate = predicate & (_.atime >= (now_ns - (int(args.amin) * 60 * 1e9)))
    if args.cmin:
        predicate = predicate & (_.ctime >= (now_ns - (int(args.cmin) * 60 * 1e9)))
    if args.crmin:
        predicate = predicate & (_.crtime >= (now_ns - (int(args.crmin) * 60 * 1e9)))

    # 5. File System Topology & Structural Coordinates
    if args.depth is not None: predicate = predicate & (_.path_depth == args.depth)
    if args.links is not None: predicate = predicate & (_.num_links == args.links)
    if args.inode is not None: predicate = predicate & (_.file_id == args.inode)

    # 6. S3 Metadata Cloud Tags
    if args.tag: predicate = predicate & (_.s3_metadata.contains(args.tag) | _.name.contains(args.tag))

    try:
        session = vastdb.connect(endpoint=config.get("vast_endpoint"), access=config.get("access_key"), secret=config.get("secret_key"), ssl_verify=False)
        start_time = time.time()
        with session.transaction() as tx:
            catalog_table = tx.catalog()
            # Projection lists all advanced columns to allow pushdown mapping
            projection = ['name', 'parent_path', 'size', 'used', 'extension', 'element_type', 'owner_name', 'group_name', 'mtime', 'atime', 'ctime', 'crtime', 'path_depth', 'num_links', 'file_id']
            reader = catalog_table.select(columns=projection, predicate=predicate)
            table = reader.read_all()
    except vastdb.errors.Forbidden:
        print("\n[!] Access Denied: Check credentials in ~/.vast-catalog-config.json\n"); sys.exit(1)
    except Exception as e:
        print(f"\n[!] Runtime Exception: {e}\n"); sys.exit(1)

    df = table.to_pandas()
    elapsed_time = time.time() - start_time
    total_found = len(df)
    df_display = df if args.limit <= 0 else df.head(args.limit)
    limit_str = "Unlimited" if args.limit <= 0 else f"max {args.limit} records shown"

    print("\n" + "="*125)
    print(f"                                      VAST DATA CATALOG ADVANCED METADATA SEARCH ENGINE")
    print("="*125)
    print(f" Query Time: {elapsed_time:.4f} sec | Matches: {total_found:,} records | Display: {limit_str}")
    print("-"*125)

    if df_display.empty:
        print(" [!] No matching records located across the query horizon layout constraints.")
    else:
        print(f" {'ELEMENT TYPE':<12} | {'OWNER':<10} | {'GROUP':<10} | {'FILE NAME':<35} | {'LOGICAL':<10} | {'PHYSICAL':<10}")
        print("-"*125)
        for idx, row in df_display.iterrows():
            name_truncated = row['name'] if len(row['name']) <= 35 else row['name'][:32] + "..."
            print(f" {row['element_type']:<12} | {row['owner_name']:<10} | {row['group_name']:<10} | {name_truncated:<35} | {format_bytes(row['size']):<10} | {format_bytes(row['used']):<10}")
    print("="*125 + "\n")

def main():
    usage_examples = """
examples:
  # [1] Core Parameter Metrics
  %(prog)s --ext c --limit 10
  %(prog)s --name memo --limit 10
  %(prog)s --ext JPEG --limit 0 > /tmp/jpeg_images.txt
  %(prog)s --name mach --type dir

  # [2] POSIX Identity & Security
  %(prog)s --user catalog --limit 5            # Filter by explicit owner username
  %(prog)s --group engineering --limit 5       # Filter by primary network group
  %(prog)s --uid 1000 --limit 5                # Filter by numeric Unix UID
  %(prog)s --gid 1000 --limit 5                # Filter by numeric Unix GID
  %(prog)s --mode 755 --limit 5                # Hunt for matching octal permissions

  # [3] Space Efficiency & Allocation
  %(prog)s --min-size 10M --limit 5            # Find logical structures >= 10MB
  %(prog)s --min-physical 1G --limit 5         # Find physical allocation >= 1GB
  %(prog)s --sparse --limit 10                 # Isolate sparse allocation maps (Logical > Physical)

  # [4] Rolling Nano-Aging Windows (Time in Minutes)
  %(prog)s --mmin 15 --limit 10                # Modified within the last 15 minutes
  %(prog)s --amin 60 --limit 10                # Read/Accessed within the last hour
  %(prog)s --cmin 30 --limit 10                # Metadata/Permissions changed in last 30 mins
  %(prog)s --crmin 1440 --limit 10              # Created brand new within the last 24 hours

  # [5] File System Topology
  %(prog)s --depth 8 --limit 5                 # Isolate deep trees sitting exactly 8 levels deep
  %(prog)s --links 2 --limit 5                 # Locate assets containing exactly 2 hard links
  %(prog)s --inode 2853735 --limit 1          # Directly target a specific system inode location

  # [6] Object Store Cloud Metadata Tags
  %(prog)s --tag quarantine --limit 0         # Search inside S3 object storage Custom TagSets
    """

    parser = argparse.ArgumentParser(
        description="High-velocity cluster-wide database search client for the VAST Data Catalog.",
        epilog=usage_examples, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # Argument declarations map directly to backend database column architecture
    parser.add_argument("--name", type=str, help="Substring containment match against asset names")
    parser.add_argument("--ext", type=str, help="Strict match against explicit file extension string")
    parser.add_argument("--type", type=str, choices=['file', 'dir'], help="Strict partition match by system element layout")
    parser.add_argument("--user", type=str, help="Filter strictly by POSIX owner name string")
    parser.add_argument("--group", type=str, help="Filter strictly by POSIX group name string")
    parser.add_argument("--uid", type=int, help="Filter strictly by numeric Unix User ID")
    parser.add_argument("--gid", type=int, help="Filter strictly by numeric Unix Group ID")
    parser.add_argument("--mode", type=str, help="Filter strictly by POSIX octal permission bits (e.g. '755', '644')")
    parser.add_argument("--min-size", type=str, help="Isolate logical files >= threshold (e.g. '10M', '2G')")
    parser.add_argument("--min-physical", type=str, help="Isolate raw block used capacity >= threshold")
    parser.add_argument("--sparse", action="store_true", help="Isolate sparse data mappings (Logical size exceeds physical footprint)")
    parser.add_argument("--mmin", type=int, help="Isolate data modified within the last N minutes")
    parser.add_argument("--amin", type=int, help="Isolate data read/accessed within the last N minutes")
    parser.add_argument("--cmin", type=int, help="Isolate data with metadata changes within the last N minutes")
    parser.add_argument("--crmin", type=int, help="Isolate data created within the last N minutes")
    parser.add_argument("--depth", type=int, help="Isolate structure located at an exact tree depth number")
    parser.add_argument("--links", type=int, help="Isolate files with a specific hard link count")
    parser.add_argument("--inode", type=int, help="Directly target a specific file metadata record ID (Inodes)")
    parser.add_argument("--tag", type=str, help="Isolate records targeting custom cloud object store S3 TagSets")
    parser.add_argument("--limit", type=int, default=20, help="Max console table outputs to print (Set to 0 for unlimited) (Default: 20)")

    args = parser.parse_args()
    if not any([args.name, args.ext, args.type, args.user, args.group, args.uid, args.gid, args.mode, args.min_size, args.min_physical, args.sparse, args.mmin, args.amin, args.cmin, args.crmin, args.depth, args.links, args.inode, args.tag]):
        parser.print_help(); print("\n[!] Error: You must specify at least one search metric filter parameter.\n"); sys.exit(1)

    search_catalog(args)

if __name__ == "__main__":
    main()
