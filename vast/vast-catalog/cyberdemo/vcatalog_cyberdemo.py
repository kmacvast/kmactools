#!/usr/bin/env python3
################################################################################
# Script Name: vcatalog_cyberdemo.py
# Description: Unified VAST Catalog cybersecurity demonstration platform.
#              Simulates ransomware activity, queries blast radius via catalog
#              pushdown, inspects raw transaction rows, and remediates the data
#              plane with async-sync aware rollback.
#
# Author: KMac kmac@vastdata.com
# Version: 1.0.0
################################################################################

import argparse
import json
import logging
import os
import queue
import random
import sys
import time
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import urllib3
import vastdb
from ibis import _

urllib3.disable_warnings()

# --- Shared Constants ---
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")
CATALOG_PATH_PREFIX = "/kmacs/vast-catalog"
TARGET_EXTENSION = "malware"
EXTENSION_SUFFIX = ".malware"
DEFAULT_MOUNT_PATH = "/mnt/kmacs-root/vast-catalog/"
MAX_AFFECTED = 5150
FILES_PER_DIR = 2
RESTORE_WORKERS = 32
SAMPLE_ROW_LIMIT = 10
ERROR_DISPLAY_LIMIT = 3

# --- Terminal Palette ---
RESET = "\033[0m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
CYAN = "\033[0;36m"
WHITE = "\033[0;37m"
LIGHT_YELLOW = "\033[93m"
BOLD = "\033[1m"
BOLD_RED = "\033[1;31m"
BOLD_GREEN = "\033[1;32m"
BOLD_YELLOW = "\033[1;33m"
BOLD_CYAN = "\033[1;36m"
BOLD_WHITE = "\033[1;37m"
DIM = "\033[2m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration & Catalog Connection
# ---------------------------------------------------------------------------

def load_vcatalog_config() -> dict:
    """Load VAST Catalog credentials and mount path from the user config file.

    Returns:
        dict: Parsed JSON configuration profile.

    Raises:
        SystemExit: If the config file is missing or invalid JSON.
    """
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        print(f"\n{BOLD_RED}Configuration Error{RESET}: Missing {DEFAULT_CONFIG_PATH}\n")
        sys.exit(1)
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            print(f"\n{BOLD_RED}Configuration Error{RESET}: Invalid JSON in {DEFAULT_CONFIG_PATH}\n")
            sys.exit(1)


def connect_catalog(config: dict):
    """Open a VAST DB session using credentials from the config profile."""
    return vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False,
    )


def resolve_mount_path(config: dict) -> str:
    """Return the local NFS mount path, normalized with a trailing slash."""
    mount = config.get("mount_path") or DEFAULT_MOUNT_PATH
    return mount if mount.endswith("/") else mount + "/"


def clean_parent_path(parent_path: str) -> str:
    """Strip the redundant catalog prefix for compact on-screen display."""
    return parent_path.removeprefix(CATALOG_PATH_PREFIX).lstrip("/")


# ---------------------------------------------------------------------------
# Terminal Report Helpers
# ---------------------------------------------------------------------------

def _hr(char: str = "=", width: int = 96, color: str = "") -> str:
    return f"{color}{char * width}{RESET}"


def _print_report_header(title: str, color: str = BOLD_YELLOW) -> None:
    print(f"\n{_hr(color=color)}")
    print(f"  {color}{title}{RESET}")
    print(_hr(color=color))


def _print_report_footer(color: str = BOLD_YELLOW) -> None:
    print(_hr(color=color) + "\n")


def _print_kv(label: str, value: str, label_width: int = 28) -> None:
    print(f"  {label:<{label_width}} {value}")


# ---------------------------------------------------------------------------
# Mode 1: Malware Simulation (--simulate-malware)
# ---------------------------------------------------------------------------

class MalwareSimulator:
    """Multi-threaded ransomware footprint simulator for the data plane."""

    def __init__(self, target_dir: str, max_affected: int = MAX_AFFECTED,
                 files_per_dir: int = FILES_PER_DIR) -> None:
        self.target_dir = target_dir
        self.max_affected = max_affected
        self.files_per_dir = files_per_dir
        self._counter_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._affected_count = 0

    def _lock_and_zip_file(self, file_path: str) -> bool:
        """Compress a source file into a .malware container and remove the original."""
        malware_path = file_path + EXTENSION_SUFFIX
        try:
            with zipfile.ZipFile(malware_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(file_path, os.path.basename(file_path))
            os.remove(file_path)
            return True
        except OSError:
            if os.path.exists(malware_path):
                os.remove(malware_path)
            return False

    def _tld_worker(self, tld_path: str) -> None:
        """Worker anchored to one top-level directory namespace."""
        logger.info("Worker started on %s", tld_path)
        empty_attempts = 0

        while not self._stop_event.is_set() and empty_attempts < 20:
            try:
                l2_dirs = [
                    os.path.join(tld_path, d)
                    for d in os.listdir(tld_path)
                    if os.path.isdir(os.path.join(tld_path, d))
                ]
            except OSError:
                l2_dirs = []

            if not l2_dirs:
                subtree = tld_path
            else:
                l2 = random.choice(l2_dirs)
                try:
                    l3_dirs = [
                        os.path.join(l2, d)
                        for d in os.listdir(l2)
                        if os.path.isdir(os.path.join(l2, d))
                    ]
                except OSError:
                    l3_dirs = []
                subtree = random.choice(l3_dirs) if l3_dirs else l2

            candidates = []
            try:
                for root, _, files in os.walk(subtree):
                    for fname in files:
                        if not fname.endswith(EXTENSION_SUFFIX):
                            candidates.append(os.path.join(root, fname))
            except OSError:
                pass

            if not candidates:
                empty_attempts += 1
                continue
            empty_attempts = 0
            random.shuffle(candidates)

            touched = 0
            for file_path in candidates:
                if touched >= self.files_per_dir:
                    break
                if self._stop_event.is_set():
                    return

                with self._counter_lock:
                    if self._affected_count >= self.max_affected:
                        self._stop_event.set()
                        return
                    self._affected_count += 1
                    snapshot = self._affected_count

                if self._lock_and_zip_file(file_path):
                    touched += 1
                    if snapshot % 500 == 0:
                        logger.info("Progress: %s files encrypted", f"{snapshot:,}")
                else:
                    with self._counter_lock:
                        self._affected_count -= 1

    def run(self) -> int:
        """Execute the simulation and print the completion report.

        Returns:
            int: Exit code (0 success, 1 failure).
        """
        if not os.path.isdir(self.target_dir):
            logger.error("Mount path not found: %s", self.target_dir)
            return 1

        tlds = [
            os.path.join(self.target_dir, d)
            for d in os.listdir(self.target_dir)
            if os.path.isdir(os.path.join(self.target_dir, d))
        ]
        if not tlds:
            logger.warning("No subdirectories found; using mount root.")
            tlds = [self.target_dir]

        logger.info("Deploying %s parallel workers across %s top-level dirs",
                    len(tlds), len(tlds))
        start = time.perf_counter()

        with ThreadPoolExecutor(max_workers=len(tlds)) as pool:
            pool.map(self._tld_worker, tlds)

        elapsed = time.perf_counter() - start
        rate = self._affected_count / elapsed if elapsed > 0 else 0.0

        _print_report_header("CYBER-INCIDENT SIMULATION — COMPLETE", BOLD_YELLOW)
        print(f"\n  {DIM}What happened:{RESET} Random workers traversed the dataset,")
        print(f"  replaced source files with compressed {BOLD_RED}*{EXTENSION_SUFFIX}{RESET} containers,")
        print(f"  and deleted the originals to mimic a ransomware blast radius.\n")

        _print_kv("Data plane mount", f"{CYAN}{self.target_dir}{RESET}")
        _print_kv("Parallel workers", f"{CYAN}{len(tlds):,}{RESET}")
        _print_kv("Files encrypted", f"{BOLD_RED}{self._affected_count:,}{RESET}")
        _print_kv("Elapsed time", f"{GREEN}{elapsed:.2f} s{RESET}")
        _print_kv("Encryption rate", f"{BOLD_WHITE}{rate:.1f} files/sec{RESET}")

        print(f"\n  {BOLD_YELLOW}Next step:{RESET} Wait 30–90 seconds for VAST Catalog to ingest")
        print(f"  the metadata changes, then run:")
        print(f"    {CYAN}--query-catalog-malware-files{RESET}  to measure blast radius")
        print(f"    {CYAN}--reset-simulation{RESET}             to restore affected files")
        _print_report_footer(BOLD_YELLOW)
        return 0


# ---------------------------------------------------------------------------
# Mode 2 & 3: Catalog Query / Raw Row Listing
# ---------------------------------------------------------------------------

class CatalogMalwareInspector:
    """Server-side VAST Catalog queries for malware extension signatures."""

    MALWARE_COLUMNS = ["name", "parent_path", "mtime", "size", "uid", "extension"]
    QUERY_COLUMNS = ["name", "parent_path", "mtime", "size", "uid"]

    def __init__(self, session) -> None:
        self.session = session

    def _fetch_malware_table(self, columns: list[str]):
        """Run a pushdown select on the indexed extension column."""
        with self.session.transaction() as tx:
            reader = tx.catalog().select(
                columns=columns,
                predicate=(
                    (_.parent_path.startswith(CATALOG_PATH_PREFIX))
                    & (_.extension == TARGET_EXTENSION)
                ),
            )
            return reader.read_all()

    def _count_total_files(self) -> int:
        """Stream-count all catalog rows under the demo path prefix."""
        total = 0
        with self.session.transaction() as tx:
            reader = tx.catalog().select(
                columns=["name"],
                predicate=_.parent_path.startswith(CATALOG_PATH_PREFIX),
            )
            for batch in reader:
                total += batch.num_rows
        return total

    def query_blast_radius(self) -> None:
        """Print a human-readable blast-radius dashboard from catalog pushdown."""
        logger.info("Querying VAST Catalog for *.%s signatures...", TARGET_EXTENSION)
        start = time.perf_counter()
        table = self._fetch_malware_table(self.QUERY_COLUMNS)
        df = table.to_pandas()
        query_elapsed = time.perf_counter() - start

        logger.info("Counting total files under %s for scale context...", CATALOG_PATH_PREFIX)
        total_files = self._count_total_files()

        affected = len(df)
        pct = (affected / total_files * 100) if total_files else 0.0

        if not df.empty:
            start_dt = df["mtime"].min()
            end_dt = df["mtime"].max()
            window = f"{start_dt.strftime('%Y-%m-%d %H:%M:%S')} → {end_dt.strftime('%H:%M:%S')} UTC"
            window_secs = int((end_dt - start_dt).total_seconds())
        else:
            window = "N/A"
            window_secs = 0

        _print_report_header("BLAST RADIUS — VAST CATALOG QUERY", BOLD_GREEN)
        print(f"\n  {DIM}How this works:{RESET} Instead of crawling the filesystem, this query")
        print(f"  uses server-side pushdown on the indexed extension column — typically")
        print(f"  sub-second even at 50 M+ file scale.\n")

        _print_kv("Catalog prefix", f"{CYAN}{CATALOG_PATH_PREFIX}{RESET}")
        _print_kv("Malware signature", f"{BOLD_RED}*.{TARGET_EXTENSION}{RESET}")
        _print_kv("Query time", f"{GREEN}{query_elapsed:.4f} s{RESET}")
        _print_kv("Compromised files", f"{BOLD_RED}{affected:,}{RESET}")
        _print_kv("Total cataloged files", f"{BOLD_CYAN}{total_files:,}{RESET}")
        _print_kv("Blast radius", f"{BOLD_YELLOW}{pct:.4f}%{RESET} of dataset")

        if affected:
            print(f"\n  {BOLD_RED}Incident window:{RESET}  {LIGHT_YELLOW}{window}{RESET}"
                  f"  ({window_secs:,} s span)")
            print(f"\n  {DIM}Showing first {SAMPLE_ROW_LIMIT} of {affected:,} matches"
                  f" (paths shortened):{RESET}\n")
            print(f"  {'FILE':<36} {'UID':<6} {'MODIFIED':<10} {'DIRECTORY'}")
            print(f"  {'-' * 90}")
            for _, row in df.head(SAMPLE_ROW_LIMIT).iterrows():
                short_path = clean_parent_path(row["parent_path"])
                print(
                    f"  {BOLD_WHITE}{row['name']:<36}{RESET} "
                    f"{row['uid']:<6} "
                    f"{LIGHT_YELLOW}{row['mtime'].strftime('%H:%M:%S'):<10}{RESET} "
                    f"{short_path}"
                )
        else:
            print(f"\n  {BOLD_GREEN}No compromised files detected.{RESET}")
            print(f"  Run {CYAN}--simulate-malware{RESET} first, wait for catalog sync,")
            print(f"  then re-run this query.")

        _print_report_footer(BOLD_GREEN)

    def list_raw_rows(self) -> None:
        """Dump unfiltered raw transaction rows for every malware extension match."""
        logger.info("Fetching raw catalog transaction rows for *.%s ...", TARGET_EXTENSION)
        table = self._fetch_malware_table(self.MALWARE_COLUMNS)
        df = table.to_pandas()

        _print_report_header("RAW CATALOG TRANSACTION ROWS", BOLD_CYAN)
        print(f"\n  {DIM}Unfiltered database records matching extension '{TARGET_EXTENSION}'"
              f" under {CATALOG_PATH_PREFIX}{RESET}\n")

        if df.empty:
            print(f"  {YELLOW}No rows returned.{RESET} The catalog index may not have synced yet.")
        else:
            pd.set_option("display.max_columns", None)
            pd.set_option("display.max_colwidth", None)
            pd.set_option("display.width", 120)
            print(df.to_string(index=False))
            print(f"\n  {DIM}Total rows: {len(df):,}{RESET}")

        _print_report_footer(BOLD_CYAN)


# ---------------------------------------------------------------------------
# Mode 4: Reset / Remediation (--reset-simulation)
# ---------------------------------------------------------------------------

class ResetEngine:
    """Catalog-guided, multi-threaded rollback with async-sync awareness."""

    def __init__(self, session, mount_path: str, workers: int = RESTORE_WORKERS) -> None:
        self.session = session
        self.mount_path = mount_path
        self.workers = workers
        self._error_queue: queue.Queue = queue.Queue()

    def _restore_file(self, row) -> str:
        """Unzip a .malware container or verify the original is already present."""
        relative = clean_parent_path(row["parent_path"])
        local_dir = os.path.join(self.mount_path, relative)
        malware_path = os.path.join(local_dir, row["name"])
        original_path = malware_path.removesuffix(EXTENSION_SUFFIX)

        if not os.path.exists(malware_path):
            if os.path.exists(original_path):
                return "VERIFIED_SAFE"
            self._error_queue.put({
                "file": row["name"],
                "path": malware_path,
                "error": "Neither .malware container nor original file found on mount.",
            })
            return "FAILED"

        try:
            with zipfile.ZipFile(malware_path, "r") as zf:
                zf.extractall(local_dir)
            os.remove(malware_path)
            return "RESTORED"
        except (OSError, zipfile.BadZipFile) as exc:
            self._error_queue.put({
                "file": row["name"],
                "path": malware_path,
                "error": str(exc),
            })
            return "FAILED"

    def run(self) -> int:
        """Query catalog, remediate data plane, and print recovery metrics."""
        logger.info("Querying catalog index for remediation targets...")
        start = time.perf_counter()

        with self.session.transaction() as tx:
            reader = tx.catalog().select(
                columns=["name", "parent_path"],
                predicate=(
                    (_.parent_path.startswith(CATALOG_PATH_PREFIX))
                    & (_.extension == TARGET_EXTENSION)
                ),
            )
            df = reader.read_all().to_pandas()

        query_elapsed = time.perf_counter() - start

        if df.empty:
            print(f"\n{BOLD_GREEN}Nothing to reset.{RESET} No *.{TARGET_EXTENSION} files in catalog.\n")
            return 0

        logger.info("Found %s targets in %.4f s — starting %s restore workers",
                    f"{len(df):,}", query_elapsed, self.workers)
        restore_start = time.perf_counter()

        restored = verified = failed = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            for status in pool.map(self._restore_file, (row for _, row in df.iterrows())):
                if status == "RESTORED":
                    restored += 1
                elif status == "VERIFIED_SAFE":
                    verified += 1
                else:
                    failed += 1

        restore_elapsed = time.perf_counter() - restore_start
        resolved = restored + verified

        _print_report_header("INCIDENT REMEDIATION — COMPLETE", BOLD_GREEN)
        print(f"\n  {DIM}How this works:{RESET} VAST Catalog instantly mapped every")
        print(f"  *.{TARGET_EXTENSION} file — no filesystem crawl required. Workers")
        print(f"  extracted originals from zip containers on the data plane.\n")

        _print_kv("Catalog lookup", f"{GREEN}{query_elapsed:.4f} s{RESET}")
        _print_kv("Data plane restore", f"{GREEN}{restore_elapsed:.2f} s{RESET}")
        _print_kv("Files restored", f"{BOLD_WHITE}{restored:,}{RESET}")
        _print_kv("Verified safe (pre-restored)", f"{CYAN}{verified:,}{RESET}")
        _print_kv("Unresolved failures", f"{BOLD_RED if failed else GREEN}{failed:,}{RESET}")
        _print_kv("Total resolved",
                  f"{BOLD_GREEN}{resolved:,}{RESET} / {len(df):,}")

        if failed == 0:
            print(f"\n  {BOLD_GREEN}All assets confirmed healthy on the data plane.{RESET}")
            print(f"  {DIM}Catalog metadata will reflect changes on the next snapshot flush.{RESET}")
        else:
            print(f"\n  {BOLD_RED}{failed} file(s) could not be remediated.{RESET}")
            print(f"  {DIM}First {ERROR_DISPLAY_LIMIT} errors:{RESET}\n")
            shown = 0
            while not self._error_queue.empty() and shown < ERROR_DISPLAY_LIMIT:
                err = self._error_queue.get()
                print(f"    File : {err['file']}")
                print(f"    Path : {err['path']}")
                print(f"    Error: {RED}{err['error']}{RESET}\n")
                shown += 1

        _print_report_footer(BOLD_GREEN)
        return 1 if failed else 0


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser with four mutually exclusive modes."""
    parser = argparse.ArgumentParser(
        description="VAST Catalog Cybersecurity Demo — simulate, detect, inspect, and recover.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --simulate-malware\n"
            "  %(prog)s --query-catalog-malware-files\n"
            "  %(prog)s --list-catalog-malware-files\n"
            "  %(prog)s --reset-simulation\n"
        ),
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--simulate-malware",
        action="store_true",
        help="Encrypt a sample of files into .malware zip containers on the data plane.",
    )
    group.add_argument(
        "--query-catalog-malware-files",
        action="store_true",
        help="Query VAST Catalog for blast-radius metrics (server-side pushdown).",
    )
    group.add_argument(
        "--list-catalog-malware-files",
        action="store_true",
        help="Dump raw catalog transaction rows for all .malware extension matches.",
    )
    group.add_argument(
        "--reset-simulation",
        action="store_true",
        help="Restore files from .malware containers using catalog-guided rollback.",
    )
    return parser


def main() -> int:
    """Dispatch the selected demo mode."""
    args = build_parser().parse_args()
    config = load_vcatalog_config()
    mount_path = resolve_mount_path(config)

    if args.simulate_malware:
        return MalwareSimulator(mount_path).run()

    session = connect_catalog(config)

    if args.query_catalog_malware_files:
        CatalogMalwareInspector(session).query_blast_radius()
        return 0

    if args.list_catalog_malware_files:
        CatalogMalwareInspector(session).list_raw_rows()
        return 0

    if args.reset_simulation:
        return ResetEngine(session, mount_path).run()

    return 1


if __name__ == "__main__":
    sys.exit(main())
