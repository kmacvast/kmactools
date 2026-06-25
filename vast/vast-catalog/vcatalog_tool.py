#!/usr/bin/env python3
################################################################################
# Script Name: vcatalog_tool.py
# Description: Unified VAST Catalog administration, audit, search, seeding,
#              and S3 tag mutation tool consolidating 12 legacy scripts.
#
# Author: KMac kmac@vastdata.com
# Version: 1.0.0
################################################################################

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from multiprocessing.pool import ThreadPool
from typing import Any

import boto3
import pandas as pd
import urllib3
import vastdb
from ibis import _

urllib3.disable_warnings()

# --- Defaults ---
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")
DEFAULT_CATALOG_PREFIX = "/kmacs/vast-catalog"
DEFAULT_MOUNT_PATH = "/mnt/kmacs-root/vast-catalog"
DEFAULT_BUCKET = "kmacs-vast-catalog-test-bucket"
DEFAULT_DATASET_URL = "https://cdn.kernel.org/pub/linux/kernel/v2.6/linux-2.6.11.tar.gz"
DEFAULT_VMS_ADDRESS = "var202.selab.vastdata.com"
DEFAULT_VMS_USER = "admin"
DICT_FILE = "/usr/share/dict/words"
WASTE_EXTENSIONS = (".tmp", ".bak", ".log")
WASTE_NAMES = ("session", "cache", "build_scratch", "old_backup", "debug_dump")

BULK_DATASETS = {
    "enron": {
        "url": "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz",
        "tmp_file": "/tmp/enron_mail.tar.gz",
        "type": "tar",
    },
    "imagenet": {
        "url": "http://cs231n.stanford.edu/tiny-imagenet-200.zip",
        "tmp_file": "/tmp/tiny-imagenet.zip",
        "type": "zip",
    },
}

SIZE_BRACKETS = {
    "Tiny (< 4KB - Metadata Inlined)": 1,
    "Small (4KB to 64KB)": 2,
    "Medium (64KB to 1MB)": 3,
    "Large (> 1MB)": 4,
}

# --- Terminal palette ---
RESET = "\033[0m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
BOLD_RED = "\033[1;31m"
BOLD_GREEN = "\033[1;32m"
BOLD_YELLOW = "\033[1;33m"
BOLD_CYAN = "\033[1;36m"
BOLD_WHITE = "\033[1;37m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Resolved runtime configuration for all tool modes."""

    config: dict
    config_path: str
    catalog_prefix: str
    mount_path: str
    bucket_name: str
    vms_address: str
    vms_user: str


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def load_config(config_path: str) -> dict:
    """Load JSON config; exit on missing or corrupt file."""
    if not os.path.exists(config_path):
        print(f"\n{BOLD_RED}Configuration Error{RESET}: Missing {config_path}\n")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            print(f"\n{BOLD_RED}Configuration Error{RESET}: Invalid JSON in {config_path}\n")
            sys.exit(1)


def build_context(args: argparse.Namespace) -> ToolContext:
    """Merge CLI overrides with config file values."""
    config_path = args.config or DEFAULT_CONFIG_PATH
    config = load_config(config_path)
    mount = args.mount_path or config.get("mount_path") or DEFAULT_MOUNT_PATH
    return ToolContext(
        config=config,
        config_path=config_path,
        catalog_prefix=args.catalog_prefix or DEFAULT_CATALOG_PREFIX,
        mount_path=mount.rstrip("/"),
        bucket_name=config.get("bucket_name") or DEFAULT_BUCKET,
        vms_address=config.get("vms_address") or DEFAULT_VMS_ADDRESS,
        vms_user=config.get("vms_user") or DEFAULT_VMS_USER,
    )


def format_bytes(size_bytes: float) -> str:
    """Convert raw byte counts to human-readable strings."""
    if size_bytes == 0:
        return "0.00 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def parse_human_size(size_str: str) -> int:
    """Parse human size strings like 10M or 2G into bytes."""
    if not size_str:
        return 0
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([KkMmGgTt]?)[Bb]?$", size_str.strip())
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    value, unit = match.groups()
    scale = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4, "": 1}[unit.lower()]
    return int(float(value) * scale)


def categorize_size(size_bytes: int) -> str:
    """Bucket file sizes into the 4-tier structural histogram grid."""
    if size_bytes < 4096:
        return "Tiny (< 4KB - Metadata Inlined)"
    if size_bytes < 65536:
        return "Small (4KB to 64KB)"
    if size_bytes < 1048576:
        return "Medium (64KB to 1MB)"
    return "Large (> 1MB)"


def clean_catalog_path(parent_path: str, catalog_prefix: str) -> str:
    """Strip catalog prefix for compact display."""
    return parent_path.removeprefix(catalog_prefix).lstrip("/")


def connect_catalog(ctx: ToolContext):
    """Open a VAST DB session."""
    return vastdb.connect(
        endpoint=ctx.config.get("vast_endpoint"),
        access=ctx.config.get("access_key"),
        secret=ctx.config.get("secret_key"),
        ssl_verify=False,
    )


def fetch_catalog_df(ctx: ToolContext, columns: list[str], predicate=None) -> pd.DataFrame:
    """Run a catalog select and return a pandas DataFrame."""
    if predicate is None:
        predicate = _.parent_path.startswith(ctx.catalog_prefix)
    session = connect_catalog(ctx)
    with session.transaction() as tx:
        table = tx.catalog().select(columns=columns, predicate=predicate).read_all()
    return table.to_pandas()


def nfs_path_to_s3_key(abs_path: str, mount_path: str) -> str:
    """Translate an absolute NFS path to an S3 object key."""
    return os.path.relpath(abs_path, mount_path)


def parse_tag_pair(tag_str: str) -> tuple[str, str]:
    """Parse key=value tag argument."""
    if "=" not in tag_str:
        print(f"{BOLD_RED}Error:{RESET} Tag must be key=value format: {tag_str}")
        sys.exit(1)
    key, value = tag_str.split("=", 1)
    return key.strip(), value.strip()


def _hr(color: str = BOLD_GREEN, width: int = 88) -> str:
    return f"{color}{'=' * width}{RESET}"


def _report_header(title: str) -> None:
    print(f"\n{_hr()}")
    print(f"  {BOLD_GREEN}{title}{RESET}")
    print(_hr())


# ---------------------------------------------------------------------------
# Mode: --show-capacity
# ---------------------------------------------------------------------------

def run_show_capacity(ctx: ToolContext) -> int:
    """Capacity profiler with 4-tier size histogram."""
    logger.info("Scanning block allocation matrix under %s", ctx.catalog_prefix)
    df = fetch_catalog_df(
        ctx, ["name", "parent_path", "size", "used", "extension", "element_type"],
    )
    df_files = df[df["element_type"] == "FILE"].copy()
    if df_files.empty:
        logger.warning("No files found for capacity profiling.")
        return 0

    total_logical = df_files["size"].sum()
    total_physical = df_files["used"].sum()
    space_delta = total_logical - total_physical

    df_files["size_bracket"] = df_files["size"].apply(categorize_size)
    histogram = (
        df_files.groupby("size_bracket")
        .agg(file_count=("name", "count"), logical_bytes=("size", "sum"), physical_bytes=("used", "sum"))
        .reset_index()
    )
    histogram["sort_key"] = histogram["size_bracket"].map(SIZE_BRACKETS)
    histogram = histogram.sort_values("sort_key")

    _report_header("CAPACITY PROFILE & DATA STRUCTURE")
    print(f"\n  {'Catalog prefix':<22} {CYAN}{ctx.catalog_prefix}{RESET}")
    print(f"  {'Global logical size':<22} {format_bytes(total_logical)}")
    print(f"  {'Global physical used':<22} {format_bytes(total_physical)}")
    print(f"  {'Net block delta':<22} {BOLD_YELLOW}{format_bytes(space_delta)}{RESET}")
    print(f"\n  {BOLD_WHITE}4-Tier Size Histogram{RESET}\n")
    for _, row in histogram.iterrows():
        print(f"  {row['size_bracket']}")
        print(f"    Files     : {row['file_count']:,}")
        print(f"    Logical   : {format_bytes(row['logical_bytes'])}"
              f"  |  Physical : {format_bytes(row['physical_bytes'])}")
        print(f"  {'─' * 60}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --show-cold-files
# ---------------------------------------------------------------------------

def run_show_cold_files(ctx: ToolContext, num_days: int) -> int:
    """Cold data and waste efficiency analysis."""
    logger.info("Querying catalog for cold-file analysis (%s-day threshold)", num_days)
    df = fetch_catalog_df(
        ctx, ["name", "parent_path", "size", "mtime", "extension", "element_type"],
    )
    df_files = df[df["element_type"] == "FILE"].copy()
    if df_files.empty:
        logger.warning("No files found under %s", ctx.catalog_prefix)
        return 0

    df_files["mtime_dt"] = pd.to_datetime(df_files["mtime"], unit="ms", errors="coerce")
    df_files["age_days"] = (pd.Timestamp.now() - df_files["mtime_dt"]).dt.days

    cold_mask = df_files["age_days"] > num_days
    scrap_mask = (
        df_files["extension"].isin([e.lstrip(".") for e in WASTE_EXTENSIONS])
        | df_files["name"].str.endswith(WASTE_EXTENSIONS, na=False)
    )
    df_cold = df_files[cold_mask]
    df_scraps = df_files[scrap_mask]

    total_files = len(df_files)
    total_footprint = df_files["size"].sum()
    df_waste = df_files[cold_mask | scrap_mask]
    waste_size = df_waste["size"].sum()
    clean_size = total_footprint - waste_size
    efficiency = (clean_size / total_footprint * 100) if total_footprint else 100.0

    _report_header("DATA RETENTION & EFFICIENCY ANALYSIS")
    print(f"\n  {'Catalog prefix':<22} {CYAN}{ctx.catalog_prefix}{RESET}")
    print(f"  {'Cold threshold':<22} {num_days} days")
    print(f"  {'Total files':<22} {total_files:,}")
    print(f"  {'Total footprint':<22} {format_bytes(total_footprint)}")
    print(f"\n  {BOLD_WHITE}Rule 1 — Cold data (>{num_days} days unmodified){RESET}")
    print(f"    Count : {len(df_cold):,}   Volume : {format_bytes(df_cold['size'].sum())}")
    print(f"\n  {BOLD_WHITE}Rule 2 — Orphaned scraps (.tmp, .bak, .log){RESET}")
    print(f"    Count : {len(df_scraps):,}   Volume : {format_bytes(df_scraps['size'].sum())}")
    print(f"\n  {BOLD_WHITE}Summary{RESET}")
    print(f"    Waste candidates : {len(df_waste):,} files / {format_bytes(waste_size)}")
    print(f"    Optimal footprint: {format_bytes(clean_size)}")
    print(f"    Efficiency ratio : {BOLD_GREEN}{efficiency:.2f}%{RESET}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --analysis-by-owner
# ---------------------------------------------------------------------------

def run_analysis_by_owner(ctx: ToolContext, uid: int | None) -> int:
    """POSIX owner consumption and world-writable exposure report."""
    logger.info("Running security audit under %s", ctx.catalog_prefix)
    df = fetch_catalog_df(
        ctx,
        ["name", "parent_path", "size", "uid", "owner_name", "nfs_mode_bits", "element_type"],
    )
    df_files = df[df["element_type"] == "FILE"].copy()
    if uid is not None:
        df_files = df_files[df_files["uid"] == uid]
    if df_files.empty:
        logger.warning("No files matched owner filter.")
        return 0

    df_files["perm_bits"] = df_files["nfs_mode_bits"].fillna(0).astype(int) & 0o777
    df_files["perm_octal"] = df_files["perm_bits"].apply(lambda x: format(x, "o").zfill(3))
    df_exposed = df_files[(df_files["perm_bits"] & 0o002) > 0]

    owner_summary = (
        df_files.groupby("owner_name")
        .agg(file_count=("name", "count"), total_bytes=("size", "sum"))
        .reset_index()
        .sort_values("total_bytes", ascending=False)
    )

    _report_header("SECURITY & PERMISSIONS BY OWNER")
    if uid is not None:
        print(f"\n  {DIM}Filtered to UID {uid}{RESET}")
    print(f"\n  {BOLD_WHITE}Storage by POSIX owner{RESET}\n")
    for _, row in owner_summary.iterrows():
        print(f"  {row['owner_name']:<16}  {row['file_count']:>8,} files"
              f"  {format_bytes(row['total_bytes']):>12}")
    print(f"\n  {BOLD_WHITE}World-writable exposures (o+w){RESET}")
    print(f"  High-risk files : {BOLD_RED}{len(df_exposed):,}{RESET}")
    if not df_exposed.empty:
        print(f"\n  {DIM}Top 5 exposures:{RESET}\n")
        for _, row in df_exposed.head(5).iterrows():
            short = clean_catalog_path(row["parent_path"], ctx.catalog_prefix)
            print(f"  [{row['perm_octal']}] {row['name']:<30}  {short}")
    else:
        print(f"  {GREEN}No world-writable files detected.{RESET}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --update-quotas
# ---------------------------------------------------------------------------

def _vastpy_cli(ctx: ToolContext, *cli_args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run vastpy-cli with VMS credentials from environment/config."""
    run_env = os.environ.copy()
    run_env["VMS_ADDRESS"] = ctx.vms_address
    run_env["VMS_USER"] = ctx.vms_user
    if env:
        run_env.update(env)
    return subprocess.run(["vastpy-cli", *cli_args], capture_output=True, text=True, env=run_env, check=False)


def run_update_quotas(ctx: ToolContext, brief: bool, vms_password: str | None) -> int:
    """Register workspace quotas and print allocation matrix."""
    password = vms_password or os.environ.get("VMS_PASSWORD") or ctx.config.get("vms_password")
    if not password:
        import getpass
        password = getpass.getpass("VMS password: ")
    env = {"VMS_PASSWORD": password}

    if not brief:
        _report_header("QUOTA REGISTRATION — STEP 1: CURRENT STATUS")
        proc = _vastpy_cli(ctx, "get", "quotas", "fields=path,used_capacity_tb,used_inodes", env=env)
        for line in proc.stdout.splitlines():
            if "used_inodes" in line or "kmacs" in line:
                print(f"  {line}")

    if not brief:
        print(f"\n  {BOLD_WHITE}Step 2 — Registering workspace quotas{RESET}")

    for path, name in [
        (f"{ctx.catalog_prefix}/linux-2.6.11", "idx_linux"),
        (f"{ctx.catalog_prefix}/workspace_1", "idx_ws1"),
    ]:
        _vastpy_cli(ctx, "post", "quotas", f"path={path}", f"name={name}", env=env)

    if os.path.isdir(ctx.mount_path):
        for entry in sorted(os.listdir(ctx.mount_path)):
            if entry.startswith("workspace_") and os.path.isdir(os.path.join(ctx.mount_path, entry)):
                vast_path = f"{ctx.catalog_prefix}/{entry}"
                if not brief:
                    print(f"  Registering {entry} → {vast_path}")
                _vastpy_cli(
                    ctx, "post", "quotas", f"path={vast_path}", f"name=idx_{entry}", env=env,
                )
    elif not brief:
        logger.warning("Mount path not accessible: %s", ctx.mount_path)

    if not brief:
        print(f"\n  {DIM}Waiting 3 s for metadata aggregation...{RESET}")
    time.sleep(3)

    _report_header("QUOTA ALLOCATION MATRIX")
    proc = _vastpy_cli(ctx, "get", "quotas", "fields=path,used_capacity_tb,used_inodes", env=env)
    rows = [ln for ln in proc.stdout.splitlines() if "kmacs" in ln]
    rows.sort(key=lambda ln: ln.split("|")[-1] if "|" in ln else ln)
    print(f"\n  {'used_inodes':<14} {'used_capacity_tb':<18} path")
    print(f"  {'─' * 70}")
    for row in rows:
        parts = [p.strip() for p in row.split("|")]
        if len(parts) >= 3:
            print(f"  {parts[0]:<14} {parts[1]:<18} {parts[2]}")
        else:
            print(f"  {row}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --search
# ---------------------------------------------------------------------------

def run_search(ctx: ToolContext, args: argparse.Namespace) -> int:
    """Multi-dimensional catalog metadata search."""
    predicate = _.parent_path.startswith(ctx.catalog_prefix)
    if args.name:
        predicate = predicate & _.name.contains(args.name)
    if args.ext:
        predicate = predicate & (_.extension == args.ext.lstrip("."))
    if args.type:
        predicate = predicate & (_.element_type == args.type.upper())
    if args.user:
        predicate = predicate & (_.owner_name == args.user)
    if args.group:
        predicate = predicate & (_.group_name == args.group)
    if args.uid is not None:
        predicate = predicate & (_.uid == args.uid)
    if args.gid is not None:
        predicate = predicate & (_.gid == args.gid)
    if args.mode:
        dec_mode = int(args.mode, 8) if args.mode.startswith("0") or len(args.mode) == 3 else int(args.mode)
        predicate = predicate & (_.nfs_mode_bits == dec_mode)
    if args.min_size:
        predicate = predicate & (_.size >= parse_human_size(args.min_size))
    if args.min_physical:
        predicate = predicate & (_.used >= parse_human_size(args.min_physical))
    if args.sparse:
        predicate = predicate & (_.size > _.used)
    now_ns = int(datetime.now().timestamp() * 1e9)
    if args.mmin:
        predicate = predicate & (_.mtime >= (now_ns - int(args.mmin) * 60 * 1e9))
    if args.amin:
        predicate = predicate & (_.atime >= (now_ns - int(args.amin) * 60 * 1e9))
    if args.cmin:
        predicate = predicate & (_.ctime >= (now_ns - int(args.cmin) * 60 * 1e9))
    if args.crmin:
        predicate = predicate & (_.crtime >= (now_ns - int(args.crmin) * 60 * 1e9))
    if args.depth is not None:
        predicate = predicate & (_.path_depth == args.depth)
    if args.links is not None:
        predicate = predicate & (_.num_links == args.links)
    if args.inode is not None:
        predicate = predicate & (_.file_id == args.inode)

    projection = [
        "name", "parent_path", "size", "used", "extension", "element_type",
        "owner_name", "group_name", "mtime", "path_depth", "num_links", "file_id",
    ]
    start = time.perf_counter()
    try:
        session = connect_catalog(ctx)
        with session.transaction() as tx:
            table = tx.catalog().select(columns=projection, predicate=predicate).read_all()
    except vastdb.errors.Forbidden:
        print(f"\n{BOLD_RED}Access Denied{RESET}: Check credentials in {ctx.config_path}\n")
        return 1
    except Exception as exc:
        print(f"\n{BOLD_RED}Search failed{RESET}: {exc}\n")
        return 1

    df = table.to_pandas()
    elapsed = time.perf_counter() - start
    limit = args.limit
    df_display = df if limit <= 0 else df.head(limit)
    limit_label = "unlimited" if limit <= 0 else f"first {limit}"

    _report_header("CATALOG METADATA SEARCH")
    print(f"\n  Query time : {GREEN}{elapsed:.4f} s{RESET}")
    print(f"  Matches    : {BOLD_CYAN}{len(df):,}{RESET}  ({limit_label} shown)")
    if df_display.empty:
        print(f"\n  {YELLOW}No matching records.{RESET}")
    else:
        print(f"\n  {'TYPE':<6} {'OWNER':<10} {'GROUP':<10} {'NAME':<32} {'LOGICAL':<10} {'PHYSICAL'}")
        print(f"  {'─' * 88}")
        for _, row in df_display.iterrows():
            name = row["name"] if len(row["name"]) <= 32 else row["name"][:29] + "..."
            print(
                f"  {row['element_type']:<6} {str(row['owner_name']):<10} {str(row['group_name']):<10}"
                f" {name:<32} {format_bytes(row['size']):<10} {format_bytes(row['used'])}"
            )
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --seed-baseline
# ---------------------------------------------------------------------------

def _download_stream(url: str, target_path: str) -> None:
    import requests
    logger.info("Downloading %s", url)
    response = requests.get(url, stream=True, timeout=60)
    response.raise_for_status()
    with open(target_path, "wb") as fh:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                fh.write(chunk)


def _seed_dummy_waste(target_dir: str, intensity_pct: int = 8) -> int:
    subdirs = []
    for root, dirs, _ in os.walk(target_dir):
        subdirs.extend(os.path.join(root, d) for d in dirs)
    if not subdirs:
        return 0
    sample_size = max(1, int(len(subdirs) * intensity_pct / 100))
    count = 0
    for subdir in random.sample(subdirs, sample_size):
        ext = random.choice(WASTE_EXTENSIONS)
        name = random.choice(WASTE_NAMES)
        path = os.path.join(subdir, f"{name}_{random.randint(100, 999)}{ext}")
        try:
            with open(path, "wb") as fh:
                fh.write(os.urandom(random.randint(1024, 256000)))
            count += 1
        except OSError:
            pass
    return count


def run_seed_baseline(ctx: ToolContext, dataset_url: str | None) -> int:
    """Download kernel tarball, extract to mount, seed waste artifacts."""
    url = dataset_url or ctx.config.get("dataset_url") or DEFAULT_DATASET_URL
    tmp_archive = "/tmp/linux-2.6.11.tar.gz"
    os.makedirs(ctx.mount_path, exist_ok=True)

    _report_header("BASELINE DATASET SEED")
    print(f"\n  Mount  : {CYAN}{ctx.mount_path}{RESET}")
    print(f"  Source : {url}\n")

    _download_stream(url, tmp_archive)
    with tarfile.open(tmp_archive, "r:gz") as tar:
        tar.extractall(path=ctx.mount_path)
    seeded = _seed_dummy_waste(ctx.mount_path)
    if os.path.exists(tmp_archive):
        os.remove(tmp_archive)

    print(f"  {GREEN}Extraction complete.{RESET} Seeded {seeded} waste artifacts.")
    print(f"  {DIM}Historical archive timestamps preserved.{RESET}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --seed-bulk
# ---------------------------------------------------------------------------

def _bulk_download(name: str, meta: dict) -> None:
    import requests
    if os.path.exists(meta["tmp_file"]) and os.path.getsize(meta["tmp_file"]) > 1_000_000:
        logger.info("Using cached %s archive", name)
        return
    logger.info("Downloading %s", name)
    response = requests.get(meta["url"], stream=True, timeout=120)
    response.raise_for_status()
    with open(meta["tmp_file"], "wb") as fh:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                fh.write(chunk)


def _bulk_extract(meta: dict, target_dir: str) -> None:
    os.makedirs(target_dir, exist_ok=True)
    if meta["type"] == "tar":
        with tarfile.open(meta["tmp_file"], "r:gz") as tar:
            tar.extractall(path=target_dir)
    else:
        with zipfile.ZipFile(meta["tmp_file"], "r") as zf:
            zf.extractall(target_dir)


def _map_tree(src_dir: str) -> tuple[list[str], list[str]]:
    dirs_list, files_list = [], []
    for root, subdirs, filenames in os.walk(src_dir):
        for sd in subdirs:
            dirs_list.append(os.path.relpath(os.path.join(root, sd), src_dir))
        for fn in filenames:
            files_list.append(os.path.relpath(os.path.join(root, fn), src_dir))
    return dirs_list, files_list


def _copy_worker(paths: tuple[str, str]) -> None:
    src, dest = paths
    if os.path.exists(src):
        shutil.copy2(src, dest)


def _parallel_clone(src_root: str, dest_root: str, threads: int) -> None:
    if not os.path.exists(src_root):
        return
    rel_dirs, rel_files = _map_tree(src_root)
    os.makedirs(dest_root, exist_ok=True)
    for d in rel_dirs:
        os.makedirs(os.path.join(dest_root, d), exist_ok=True)
    tasks = [(os.path.join(src_root, f), os.path.join(dest_root, f)) for f in rel_files]
    pool = ThreadPool(threads)
    pool.map(_copy_worker, tasks)
    pool.close()
    pool.join()


def run_seed_bulk(ctx: ToolContext, copies: int) -> int:
    """Download Enron + Tiny ImageNet and clone workspace arrays."""
    scratch = "/tmp/vast_scratch_seed"
    threads = max(32, (os.cpu_count() or 8) * 4)

    _report_header("BULK WORKLOAD SEED")
    print(f"\n  Mount   : {CYAN}{ctx.mount_path}{RESET}")
    print(f"  Copies  : {copies}   Threads : {threads}\n")

    for name, meta in BULK_DATASETS.items():
        _bulk_download(name, meta)
        _bulk_extract(meta, scratch)

    enron_src = os.path.join(scratch, "enron_mail_20150507", "maildir")
    if not os.path.exists(enron_src):
        enron_src = os.path.join(scratch, "maildir")
    imagenet_src = os.path.join(scratch, "tiny-imagenet-200")

    for i in range(1, copies + 1):
        ws = os.path.join(ctx.mount_path, f"workspace_{i}")
        logger.info("Cloning workspace %s/%s → %s", i, copies, ws)
        _parallel_clone(enron_src, os.path.join(ws, "corporate_email"), threads)
        _parallel_clone(imagenet_src, os.path.join(ws, "ml_training_images"), threads)

    if os.path.exists(scratch):
        shutil.rmtree(scratch)
    print(f"\n  {GREEN}Bulk seed complete — {copies} workspaces created.{RESET}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# Mode: --copy-infinitely
# ---------------------------------------------------------------------------

class _InfiniteCopier:
    """Persistent dictionary-driven fpsync multiplication loop."""

    def __init__(self, ctx: ToolContext) -> None:
        self.ctx = ctx
        self._stop = False
        self.src_ws1 = os.path.join(ctx.mount_path, "workspace_1a")
        self.src_ws2 = os.path.join(ctx.mount_path, "workspace_2a")
        self.log_dir = "/tmp/fpart_copy_logs"
        self._active: list[subprocess.Popen] = []

    def _handle_signal(self, *_args) -> None:
        self._stop = True
        for proc in self._active:
            proc.terminate()
        print(f"\n{YELLOW}Interrupt received — stopping workers.{RESET}")

    def _random_word(self) -> str:
        if os.path.isfile(DICT_FILE):
            with open(DICT_FILE, encoding="utf-8", errors="ignore") as fh:
                words = [w.strip().lower() for w in fh if w.strip().isalnum()]
            if words:
                return random.choice(words)
        return f"run_{random.randint(10000, 99999)}"

    def run(self) -> int:
        if not shutil.which("fpsync"):
            print(f"{BOLD_RED}Error:{RESET} fpsync not found in PATH")
            return 1
        for src in (self.src_ws1, self.src_ws2):
            if not os.path.isdir(src):
                print(f"{BOLD_RED}Error:{RESET} Source missing: {src}")
                return 1
        os.makedirs(self.log_dir, exist_ok=True)
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        _report_header("INFINITE COPY ENGINE")
        print(f"\n  {DIM}Press Ctrl+C to stop. Random dictionary words drive dest names.{RESET}\n")

        block = 0
        while not self._stop:
            word = self._random_word()
            dest1 = os.path.join(self.ctx.mount_path, f"workspace_1_{word}")
            dest2 = os.path.join(self.ctx.mount_path, f"workspace_2_{word}")
            if os.path.exists(dest1) or os.path.exists(dest2):
                continue
            block += 1
            log1 = os.path.join(self.log_dir, f"fpsync_ws1_{word}.log")
            log2 = os.path.join(self.log_dir, f"fpsync_ws2_{word}.log")
            print(f"  Block {block}: copying to workspace_1_{word} / workspace_2_{word}")
            self._active = [
                subprocess.Popen(
                    ["fpsync", "-n", "32", "-v", self.src_ws1, dest1 + "/"],
                    stdout=open(log1, "w"), stderr=subprocess.STDOUT,
                ),
                subprocess.Popen(
                    ["fpsync", "-n", "32", "-v", self.src_ws2, dest2 + "/"],
                    stdout=open(log2, "w"), stderr=subprocess.STDOUT,
                ),
            ]
            for proc in self._active:
                proc.wait()
            self._active = []
        return 0


def run_copy_infinitely(ctx: ToolContext) -> int:
    return _InfiniteCopier(ctx).run()


# ---------------------------------------------------------------------------
# Mode: --show-schema
# ---------------------------------------------------------------------------

def run_show_schema(ctx: ToolContext) -> int:
    """Print raw catalog arrow_schema column dictionary."""
    session = connect_catalog(ctx)
    with session.transaction() as tx:
        schema = tx.catalog().arrow_schema

    _report_header("CATALOG SCHEMA — arrow_schema")
    print()
    for field in schema:
        print(f"  {field.name:<24} {field.type}")
    print(f"\n  {DIM}Total columns: {len(schema)}{RESET}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# S3 tag mutation (--add-s3-tag / --modify-s3-tag / --delete-s3-tag)
# ---------------------------------------------------------------------------

def _s3_client(ctx: ToolContext):
    return boto3.client(
        "s3",
        endpoint_url=ctx.config.get("vast_endpoint"),
        aws_access_key_id=ctx.config.get("access_key"),
        aws_secret_access_key=ctx.config.get("secret_key"),
        verify=False,
    )


def _get_existing_tags(client, bucket: str, key: str) -> dict[str, str]:
    try:
        resp = client.get_object_tagging(Bucket=bucket, Key=key)
        return {t["Key"]: t["Value"] for t in resp.get("TagSet", [])}
    except client.exceptions.NoSuchKey:
        print(f"{BOLD_RED}Error:{RESET} S3 object not found: {key}")
        sys.exit(1)


def _put_tags(client, bucket: str, key: str, tags: dict[str, str]) -> None:
    client.put_object_tagging(
        Bucket=bucket,
        Key=key,
        Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in tags.items()]},
    )


def run_s3_tag_mutation(
    ctx: ToolContext, s3_target: str, add: str | None, modify: str | None, delete: str | None,
) -> int:
    """Add, modify, or delete S3 tags on a single NFS-backed object."""
    if not os.path.isabs(s3_target):
        print(f"{BOLD_RED}Error:{RESET} --s3-target must be an absolute path")
        return 1
    key = nfs_path_to_s3_key(s3_target, ctx.mount_path)
    client = _s3_client(ctx)
    tags = _get_existing_tags(client, ctx.bucket_name, key)

    if add:
        k, v = parse_tag_pair(add)
        tags[k] = v
        action = f"Added tag {k}={v}"
    elif modify:
        k, v = parse_tag_pair(modify)
        if k not in tags:
            print(f"{YELLOW}Warning:{RESET} Tag key '{k}' did not exist — creating it.")
        tags[k] = v
        action = f"Modified tag {k}={v}"
    elif delete:
        if delete not in tags:
            print(f"{YELLOW}Warning:{RESET} Tag key '{delete}' not present.")
        else:
            del tags[delete]
        action = f"Deleted tag {delete}"
    else:
        return 1

    _put_tags(client, ctx.bucket_name, key, tags)
    _report_header("S3 TAG MUTATION")
    print(f"\n  Target : {s3_target}")
    print(f"  S3 key : {key}")
    print(f"  Action : {GREEN}{action}{RESET}")
    print(f"\n  Current tags:")
    for tk, tv in sorted(tags.items()):
        print(f"    {tk} = {tv}")
    print(f"\n{_hr()}\n")
    return 0


# ---------------------------------------------------------------------------
# CLI router
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the unified argparse router."""
    parser = argparse.ArgumentParser(
        description="VAST Catalog unified administration tool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --show-capacity\n"
            "  %(prog)s --show-cold-files --num-days 180\n"
            "  %(prog)s --analysis-by-owner --uid 1000\n"
            "  %(prog)s --update-quotas --brief\n"
            "  %(prog)s --search --ext JPEG --limit 10\n"
            "  %(prog)s --seed-baseline\n"
            "  %(prog)s --seed-bulk --copies 3\n"
            "  %(prog)s --show-schema\n"
            "  %(prog)s --add-s3-tag 'owner=team' --s3-target /mnt/.../file.tmp\n"
        ),
    )

    # Global connection parameters
    parser.add_argument("--config", type=str, help=f"Config file (default: {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--catalog-prefix", type=str, help=f"Catalog query root (default: {DEFAULT_CATALOG_PREFIX})")
    parser.add_argument("--mount-path", type=str, help="NFS mount path override")

    # Mutually exclusive core modes
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--show-capacity", action="store_true", help="Capacity profiler + size histogram")
    mode.add_argument("--show-cold-files", action="store_true", help="Cold data & waste efficiency report")
    mode.add_argument("--analysis-by-owner", action="store_true", help="Owner consumption & permission audit")
    mode.add_argument("--update-quotas", action="store_true", help="Register and report workspace quotas")
    mode.add_argument("--search", action="store_true", help="Multi-dimensional metadata search")
    mode.add_argument("--seed-baseline", action="store_true", help="Download kernel tarball baseline seed")
    mode.add_argument("--seed-bulk", action="store_true", help="Bulk Enron + ImageNet workspace clone")
    mode.add_argument("--copy-infinitely", action="store_true", help="Infinite dictionary-driven copy loop")
    mode.add_argument("--show-schema", action="store_true", help="Print catalog arrow_schema columns")
    mode.add_argument("--add-s3-tag", type=str, metavar="KEY=VALUE", help="Add S3 tag to --s3-target file")
    mode.add_argument("--modify-s3-tag", type=str, metavar="KEY=VALUE", help="Modify existing S3 tag")
    mode.add_argument("--delete-s3-tag", type=str, metavar="KEY", help="Delete S3 tag key")

    # Mode-specific options
    parser.add_argument("--num-days", type=int, default=365, help="Cold-file age threshold (default: 365)")
    parser.add_argument("--uid", type=int, help="Filter owner analysis to a single UID")
    parser.add_argument("--brief", action="store_true", help="Quotas: final table only")
    parser.add_argument("--vms-password", type=str, help="VMS password for quota operations")
    parser.add_argument("--copies", type=int, default=5, help="Bulk seed workspace copies (default: 5)")
    parser.add_argument("--dataset-url", type=str, help="Override baseline seed download URL")
    parser.add_argument("--s3-target", type=str, help="Absolute NFS path for S3 tag mutation")

    # Search filters
    parser.add_argument("--name", type=str, help="Search: name substring")
    parser.add_argument("--ext", type=str, help="Search: file extension")
    parser.add_argument("--type", type=str, choices=["file", "dir"], help="Search: element type")
    parser.add_argument("--user", type=str, help="Search: POSIX owner name")
    parser.add_argument("--group", type=str, help="Search: POSIX group name")
    parser.add_argument("--gid", type=int, help="Search: numeric GID")
    parser.add_argument("--mode", type=str, help="Search: POSIX mode octal")
    parser.add_argument("--min-size", type=str, help="Search: minimum logical size")
    parser.add_argument("--min-physical", type=str, help="Search: minimum physical size")
    parser.add_argument("--sparse", action="store_true", help="Search: sparse files (logical > physical)")
    parser.add_argument("--mmin", type=int, help="Search: modified within N minutes")
    parser.add_argument("--amin", type=int, help="Search: accessed within N minutes")
    parser.add_argument("--cmin", type=int, help="Search: changed within N minutes")
    parser.add_argument("--crmin", type=int, help="Search: created within N minutes")
    parser.add_argument("--depth", type=int, help="Search: exact path depth")
    parser.add_argument("--links", type=int, help="Search: hard link count")
    parser.add_argument("--inode", type=int, help="Search: file_id / inode")
    parser.add_argument("--limit", type=int, default=20, help="Search result limit (0 = unlimited)")

    return parser


def _search_filters_present(args: argparse.Namespace) -> bool:
    return any([
        args.name, args.ext, args.type, args.user, args.group,
        args.uid, args.gid, args.mode, args.min_size, args.min_physical,
        args.sparse, args.mmin, args.amin, args.cmin, args.crmin,
        args.depth is not None, args.links is not None, args.inode is not None,
    ])


def main(argv: list[str] | None = None) -> int:
    """Dispatch the selected tool mode."""
    parser = build_parser()
    args = parser.parse_args(argv)
    ctx = build_context(args)

    if args.show_capacity:
        return run_show_capacity(ctx)
    if args.show_cold_files:
        return run_show_cold_files(ctx, args.num_days)
    if args.analysis_by_owner:
        return run_analysis_by_owner(ctx, args.uid)
    if args.update_quotas:
        return run_update_quotas(ctx, args.brief, args.vms_password)
    if args.search:
        if not _search_filters_present(args):
            parser.error("--search requires at least one filter (--ext, --name, etc.)")
        return run_search(ctx, args)
    if args.seed_baseline:
        return run_seed_baseline(ctx, args.dataset_url)
    if args.seed_bulk:
        return run_seed_bulk(ctx, args.copies)
    if args.copy_infinitely:
        return run_copy_infinitely(ctx)
    if args.show_schema:
        return run_show_schema(ctx)

    # S3 tag mutations
    s3_ops = sum(1 for x in (args.add_s3_tag, args.modify_s3_tag, args.delete_s3_tag) if x)
    if s3_ops:
        if s3_ops > 1:
            parser.error("Specify only one of --add-s3-tag, --modify-s3-tag, --delete-s3-tag")
        if not args.s3_target:
            parser.error("S3 tag operations require --s3-target <absolute-path>")
        return run_s3_tag_mutation(ctx, args.s3_target, args.add_s3_tag, args.modify_s3_tag, args.delete_s3_tag)

    return 1


if __name__ == "__main__":
    sys.exit(main())
