#!/usr/bin/env python3
################################################################################
# Script Name: find_files_oldschool.py
# Description: Optimized brute-force NFS filesystem crawl benchmark. Fans out
#              parallel GNU find workers across the mount tree to locate *.malware
#              files — the native-OS baseline to compare against VAST Catalog.
#
# Author: KMac kmac@vastdata.com
# Version: 1.1.0
################################################################################

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

# --- Constants ---
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")
DEFAULT_MOUNT_PATH = "/mnt/kmacs-root/vast-catalog/"
TARGET_GLOB = "*.malware"
TARGET_EXTENSION = "malware"
DEFAULT_THREADS = 64
SAMPLE_LIMIT = 10

# --- Terminal Palette ---
RESET = "\033[0m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
BOLD_RED = "\033[1;31m"
BOLD_GREEN = "\033[1;32m"
BOLD_YELLOW = "\033[1;33m"
BOLD_WHITE = "\033[1;37m"

_GNU_FIND_O3: bool | None = None


@dataclass
class JobResult:
    """Outcome of a single parallel find worker."""

    root: str
    maxdepth: int | None
    elapsed: float
    matches: int
    error: str | None = None


@dataclass
class CrawlStats:
    """Aggregated metrics for a full crawl run."""

    wall_seconds: float
    total_matches: int
    preview: list[str] = field(default_factory=list)
    jobs: list[JobResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def jobs_ok(self) -> int:
        return sum(1 for j in self.jobs if j.error is None)

    @property
    def jobs_failed(self) -> int:
        return sum(1 for j in self.jobs if j.error is not None)

    @property
    def matches_per_sec(self) -> float:
        return self.total_matches / self.wall_seconds if self.wall_seconds > 0 else 0.0

    @property
    def avg_job_seconds(self) -> float:
        return sum(j.elapsed for j in self.jobs) / len(self.jobs) if self.jobs else 0.0

    @property
    def slowest_job(self) -> JobResult | None:
        return max(self.jobs, key=lambda j: j.elapsed) if self.jobs else None

    @property
    def fastest_job(self) -> JobResult | None:
        return min(self.jobs, key=lambda j: j.elapsed) if self.jobs else None

    @property
    def jobs_with_hits(self) -> int:
        return sum(1 for j in self.jobs if j.matches > 0)


def _format_duration(seconds: float) -> str:
    """Render seconds as a human-readable duration string."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} seconds"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:.2f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h {int(minutes)}m {secs:.2f}s"


def _short_path(path: str, mount_path: str, max_len: int = 52) -> str:
    """Trim a path for display, relative to the mount when possible."""
    prefix = mount_path.rstrip("/") + "/"
    label = path.removeprefix(prefix)
    return label if len(label) <= max_len else "…" + label[-(max_len - 1):]


def load_config() -> dict:
    """Load VAST Catalog config for mount_path resolution."""
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        print(f"\n{BOLD_RED}Configuration Error{RESET}: Missing {DEFAULT_CONFIG_PATH}\n")
        sys.exit(1)
    with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError:
            print(f"\n{BOLD_RED}Configuration Error{RESET}: Invalid JSON in {DEFAULT_CONFIG_PATH}\n")
            sys.exit(1)


def resolve_mount_path(config: dict) -> str:
    """Return mount path with trailing slash."""
    mount = config.get("mount_path") or DEFAULT_MOUNT_PATH
    return mount if mount.endswith("/") else mount + "/"


def _gnu_find_o3_supported() -> bool:
    """Detect GNU find so we can pass -O3 (aggressive stat optimization)."""
    global _GNU_FIND_O3
    if _GNU_FIND_O3 is not None:
        return _GNU_FIND_O3
    try:
        proc = subprocess.run(
            ["find", "--version"], capture_output=True, text=True, timeout=5, check=False,
        )
        _GNU_FIND_O3 = "GNU findutils" in (proc.stdout + proc.stderr)
    except (OSError, subprocess.TimeoutExpired):
        _GNU_FIND_O3 = False
    return _GNU_FIND_O3


def _build_find_cmd(scan_root: str, maxdepth: int | None = None) -> list[str]:
    """Assemble the fastest find invocation for extension-only matching."""
    cmd = ["find", scan_root, "-type", "f", "-name", TARGET_GLOB]
    if _gnu_find_o3_supported():
        cmd[1:1] = ["-O3"]
    if maxdepth is not None:
        cmd.extend(["-maxdepth", str(maxdepth)])
    return cmd


def discover_scan_roots(mount_path: str, target_parallelism: int) -> list[tuple[str, int | None]]:
    """Return disjoint (path, maxdepth) pairs for parallel find workers."""
    try:
        tlds = sorted(
            os.path.join(mount_path, entry)
            for entry in os.listdir(mount_path)
            if os.path.isdir(os.path.join(mount_path, entry))
        )
    except OSError:
        tlds = []

    if not tlds:
        return [(mount_path.rstrip("/"), None)]

    if len(tlds) >= target_parallelism:
        return [(tld, None) for tld in tlds]

    jobs: list[tuple[str, int | None]] = []
    for tld in tlds:
        try:
            subdirs = sorted(
                os.path.join(tld, entry)
                for entry in os.listdir(tld)
                if os.path.isdir(os.path.join(tld, entry))
            )
        except OSError:
            subdirs = []
        if subdirs:
            jobs.append((tld, 1))
            jobs.extend((sub, None) for sub in subdirs)
        else:
            jobs.append((tld, None))

    return jobs if jobs else [(mount_path.rstrip("/"), None)]


def _scan_root(scan_root: str, out_path: str, maxdepth: int | None = None) -> JobResult:
    """Run find on one root, writing matches to a dedicated temp file."""
    start = time.perf_counter()
    cmd = _build_find_cmd(scan_root, maxdepth)
    try:
        with open(out_path, "w", encoding="utf-8") as out_fh:
            proc = subprocess.run(
                cmd, stdout=out_fh, stderr=subprocess.PIPE, text=True, check=False,
            )
        elapsed = time.perf_counter() - start
        if proc.returncode not in (0, 1):
            err = proc.stderr.strip() or f"find exited {proc.returncode}"
            return JobResult(scan_root, maxdepth, elapsed, 0, err)
        matches = sum(1 for _ in open(out_path, encoding="utf-8"))
        return JobResult(scan_root, maxdepth, elapsed, matches)
    except OSError as exc:
        return JobResult(scan_root, maxdepth, time.perf_counter() - start, 0, str(exc))


def run_crawl(mount_path: str, threads: int,
              scan_jobs: list[tuple[str, int | None]]) -> CrawlStats:
    """Execute parallel find crawl and return aggregated run statistics."""
    workers = min(len(scan_jobs), threads)

    tmpdir = tempfile.mkdtemp(prefix="oldschool_find_")
    job_to_file = {
        (root, depth): os.path.join(tmpdir, f"hits_{idx:04d}.txt")
        for idx, (root, depth) in enumerate(scan_jobs)
    }

    wall_start = time.perf_counter()
    job_results: list[JobResult] = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(_scan_root, root, path, depth)
            for (root, depth), path in job_to_file.items()
        ]
        for fut in as_completed(futures):
            job_results.append(fut.result())

    wall_seconds = time.perf_counter() - wall_start

    preview: list[str] = []
    total = 0
    for path in job_to_file.values():
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                total += 1
                if len(preview) < SAMPLE_LIMIT:
                    preview.append(line.rstrip("\n"))

    for path in job_to_file.values():
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass

    errors = []
    for job in job_results:
        if job.error:
            label = f"{job.root} (maxdepth={job.maxdepth})" if job.maxdepth else job.root
            errors.append(f"{label}: {job.error}")

    return CrawlStats(
        wall_seconds=wall_seconds,
        total_matches=total,
        preview=preview,
        jobs=sorted(job_results, key=lambda j: j.elapsed, reverse=True),
        errors=errors,
    )


def _hr(color: str = BOLD_GREEN, width: int = 96) -> str:
    return f"{color}{'=' * width}{RESET}"


def print_report(mount_path: str, threads: int, scan_jobs: list[tuple[str, int | None]],
                 stats: CrawlStats) -> None:
    """Render the post-run benchmark summary with timing and crawl heuristics."""
    find_mode = "GNU find -O3" if _gnu_find_o3_supported() else "standard find"
    workers = min(len(scan_jobs), threads)
    slow = stats.slowest_job
    fast = stats.fastest_job

    print(f"\n{_hr(BOLD_GREEN)}")
    print(f"  {BOLD_GREEN}SCAN COMPLETE — RUN SUMMARY{RESET}")
    print(_hr(BOLD_GREEN))

    print(f"\n  {BOLD_WHITE}Timing{RESET}")
    print(f"  {'─' * 50}")
    print(f"  {'Total wall-clock time':<26} {BOLD_RED}{_format_duration(stats.wall_seconds)}{RESET}"
          f"  {DIM}({stats.wall_seconds:.3f} s){RESET}")
    if stats.jobs:
        print(f"  {'Avg time per scan job':<26} {_format_duration(stats.avg_job_seconds)}")
        if slow:
            print(f"  {'Slowest scan job':<26} {_format_duration(slow.elapsed)}"
                  f"  {DIM}{_short_path(slow.root, mount_path)}{RESET}")
        if fast and len(stats.jobs) > 1:
            print(f"  {'Fastest scan job':<26} {_format_duration(fast.elapsed)}"
                  f"  {DIM}{_short_path(fast.root, mount_path)}{RESET}")

    print(f"\n  {BOLD_WHITE}Results{RESET}")
    print(f"  {'─' * 50}")
    print(f"  {'Target signature':<26} {BOLD_YELLOW}{TARGET_GLOB}{RESET}")
    print(f"  {'Files found':<26} {BOLD_RED}{stats.total_matches:,}{RESET}")
    print(f"  {'Match discovery rate':<26} {BOLD_WHITE}{stats.matches_per_sec:,.1f} files/sec{RESET}")
    if stats.total_matches == 0:
        print(f"  {DIM}No matches — run vcatalog_cyberdemo.py --simulate-malware first.{RESET}")

    print(f"\n  {BOLD_WHITE}Execution{RESET}")
    print(f"  {'─' * 50}")
    print(f"  {'Mount path':<26} {CYAN}{mount_path}{RESET}")
    print(f"  {'Parallel workers':<26} {YELLOW}{workers}{RESET}"
          f"  {DIM}({len(scan_jobs)} disjoint jobs){RESET}")
    print(f"  {'Jobs succeeded':<26} {GREEN}{stats.jobs_ok}{RESET} / {len(scan_jobs)}")
    if stats.jobs_failed:
        print(f"  {'Jobs failed':<26} {BOLD_RED}{stats.jobs_failed}{RESET}")
    print(f"  {'Jobs with matches':<26} {stats.jobs_with_hits} / {len(scan_jobs)}")
    print(f"  {'Find engine':<26} {find_mode}")

    print(f"\n  {BOLD_WHITE}Benchmark context{RESET}")
    print(f"  {'─' * 50}")
    print(f"  {DIM}This is the native POSIX crawl baseline. Compare against:{RESET}")
    print(f"    {CYAN}vcatalog_cyberdemo.py --query-catalog-malware-files{RESET}")
    print(f"  {DIM}VAST Catalog pushdown typically returns in under 4 seconds at 50M+ scale.{RESET}")
    if stats.wall_seconds > 4 and stats.total_matches > 0:
        speedup = stats.wall_seconds / 4.0
        print(f"  {DIM}At a 4 s catalog reference, this crawl was ~{speedup:,.0f}× slower.{RESET}")

    if stats.errors:
        print(f"\n  {BOLD_YELLOW}Worker warnings ({len(stats.errors)}):{RESET}")
        for msg in stats.errors[:3]:
            print(f"    {msg}")

    if stats.total_matches > 0:
        print(f"\n  {BOLD_WHITE}Sample matches{RESET} {DIM}(first {min(SAMPLE_LIMIT, stats.total_matches)}"
              f" of {stats.total_matches:,}, mount prefix stripped){RESET}\n")
        prefix = mount_path.rstrip("/") + "/"
        for path in stats.preview:
            print(f"    {path.removeprefix(prefix)}")

    print(f"\n{_hr(BOLD_GREEN)}\n")


def build_parser() -> argparse.ArgumentParser:
    """CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Old-school parallel find benchmark for *.malware files over NFS.",
    )
    parser.add_argument(
        "--threads", type=int, default=DEFAULT_THREADS,
        help=f"Max parallel find workers (default: {DEFAULT_THREADS})",
    )
    return parser


def main() -> int:
    """Entry point."""
    args = build_parser().parse_args()
    if args.threads < 1:
        print(f"{BOLD_RED}Error:{RESET} --threads must be >= 1")
        return 1

    config = load_config()
    mount_path = resolve_mount_path(config)

    if not os.path.isdir(mount_path):
        print(f"\n{BOLD_RED}Error:{RESET} Mount path not found: {mount_path}\n")
        return 1

    scan_jobs = discover_scan_roots(mount_path, args.threads)
    print(f"\n{BOLD_GREEN}{'=' * 70}{RESET}")
    print(f"  {BOLD_WHITE}OPTIMIZED NATIVE LINUX BLAST RADIUS BENCHMARK{RESET}")
    print(f"{BOLD_GREEN}{'=' * 70}{RESET}")
    print(f"  Target Directory : {CYAN}{mount_path}{RESET}")
    print(f"  Parallel Threads : {YELLOW}{args.threads}{RESET}")
    print(f"  Target Signature : {BOLD_YELLOW}{TARGET_GLOB}{RESET}")
    print(f"{BOLD_GREEN}{'=' * 70}{RESET}")
    print(f"{DIM}Crawling filesystem — this may take minutes at scale...{RESET}\n")

    stats = run_crawl(mount_path, args.threads, scan_jobs)
    print_report(mount_path, args.threads, scan_jobs, stats)
    return 1 if stats.errors and stats.total_matches == 0 else 0


if __name__ == "__main__":
    sys.exit(main())
