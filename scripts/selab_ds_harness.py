#!/usr/bin/env python3
################################################################################
# Script: selab_ds_harness.py
# Descr: Run VAST GNS DataSpace visibility and IO stress tests across two
#        mounted cluster paths. Requires an explicit test mode. Supports simple
#        heartbeat logging, sequential write, sequential read, random read,
#        random write, and a mixed simultaneous IO stress mode.
# Date: 2026-05-27
# Author: KMac
#
# Usage:
#
#    python3 ~/scripts/selab_ds_harness.py --simple --duration 300
#
#    python3 ~/scripts/selab_ds_harness.py --sequential-write --size 10MB --duration 300
#    python3 ~/scripts/selab_ds_harness.py --sequential-read  --size 10MB --duration 300
#    python3 ~/scripts/selab_ds_harness.py --random-read      --size 4KB  --duration 300
#    python3 ~/scripts/selab_ds_harness.py --random-write     --size 4KB  --duration 300
#    python3 ~/scripts/selab_ds_harness.py --go-crazy --duration 300
#
#    Open a SECOND terminal window and tail the shared logfile:
#
#       tail -f /mnt/var203/dataspace/combined_output_log.txt
#
# Notes:
#
#    - The script intentionally does not stream test output to stdout.
#    - Every logfile write is followed by fsync() and sync().
#    - Cluster names are color-coded in the second column.
#    - --go-crazy uses simultaneous mixed IO from both mount points against
#      the same shared file with 47KiB random IO plus larger reads and writes.
#
################################################################################

import argparse
import os
import random
import re
import sys
import time
import json
import fcntl
from multiprocessing import Process

CLUSTERS = ["var202", "var203"]
BASE_DIR = "/mnt"
DATASPACE = "dataspace"
OUTFILE = "combined_output_log.txt"
SEQ_FILE = "gns_sequential_payload.bin"
RAND_FILE = "gns_random_payload.bin"
CRAZY_FILE = "gns_go_crazy_shared.bin"
LOCK_FILE = "gns_nfs_lock_stress.lock"

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RESET = "\033[0m"

CLUSTER_COLORS = {
    "var202": MAGENTA,
    "var203": CYAN,
}


def parse_size(value):
    match = re.match(r"^([0-9]+)(B|KB|MB|GB|KiB|MiB|GiB)?$", value)
    if not match:
        raise argparse.ArgumentTypeError(f"Invalid size: {value}")

    num = int(match.group(1))
    unit = match.group(2) or "B"

    units = {
        "B": 1,
        "KB": 1000,
        "MB": 1000 * 1000,
        "GB": 1000 * 1000 * 1000,
        "KiB": 1024,
        "MiB": 1024 * 1024,
        "GiB": 1024 * 1024 * 1024,
    }

    return num * units[unit]


def dts():
    return time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000000):06d}"


def cluster_path(cluster):
    return os.path.join(BASE_DIR, cluster, DATASPACE)


def log_path(cluster):
    return os.path.join(cluster_path(cluster), OUTFILE)


def color_cluster(cluster):
    return f"{CLUSTER_COLORS.get(cluster, GREEN)}{cluster}{RESET}"


def log_line(cluster, status_color, message):
    line = f"{CYAN}{dts()}{RESET} | {color_cluster(cluster)} | {status_color}{message}{RESET}\n"
    path = log_path(cluster)

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

    os.sync()


def validate_mounts():
    for cluster in CLUSTERS:
        path = cluster_path(cluster)

        if not os.path.isdir(path):
            print(f"ERROR: Directory does not exist: {path}", file=sys.stderr)
            sys.exit(1)

        if not os.access(path, os.W_OK):
            print(f"ERROR: Cannot write to: {path}", file=sys.stderr)
            sys.exit(1)


def opposite_cluster(cluster):
    return CLUSTERS[1] if cluster == CLUSTERS[0] else CLUSTERS[0]


def write_random_file(path, size_bytes):
    chunk_size = min(1024 * 1024, size_bytes)
    remaining = size_bytes

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        while remaining > 0:
            this_write = min(chunk_size, remaining)
            os.write(fd, os.urandom(this_write))
            remaining -= this_write
        os.fsync(fd)
    finally:
        os.close(fd)

    os.sync()


def ensure_file(path, size_bytes):
    if not os.path.exists(path) or os.path.getsize(path) < size_bytes:
        write_random_file(path, size_bytes)


def simple(cluster):
    log_line(cluster, GREEN, "simple heartbeat written, fsync completed, sync completed")


def sequential_write(cluster, size_bytes, size_text):
    path = os.path.join(cluster_path(cluster), SEQ_FILE)

    try:
        write_random_file(path, size_bytes)
        log_line(cluster, GREEN, f"sequential write completed, size={size_text}, fsync completed, sync completed")
    except Exception as exc:
        log_line(cluster, RED, f"sequential write failed, size={size_text}, error={exc}")


def sequential_read(cluster, size_bytes, size_text):
    remote = opposite_cluster(cluster)
    path = os.path.join(cluster_path(remote), SEQ_FILE)

    try:
        ensure_file(path, max(size_bytes, 64 * 1024 * 1024))

        with open(path, "rb", buffering=0) as handle:
            remaining = size_bytes
            while remaining > 0:
                data = handle.read(min(1024 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)

        os.sync()
        log_line(cluster, GREEN, f"sequential read completed from {remote}, size={size_text}, sync completed")
    except Exception as exc:
        log_line(cluster, RED, f"sequential read failed from {remote}, size={size_text}, error={exc}")



def random_read(cluster, size_bytes, size_text, read_duration):
    remote = opposite_cluster(cluster)
    path = os.path.join(cluster_path(remote), RAND_FILE)
    reads = 0

    try:
        ensure_file(path, 64 * 1024 * 1024)
        file_size = os.path.getsize(path)
        max_offset = max(0, file_size - size_bytes)
        end_time = time.time() + read_duration

        with open(path, "rb", buffering=0) as handle:
            while time.time() < end_time:
                offset = random.randint(0, max_offset)
                handle.seek(offset)
                handle.read(size_bytes)
                reads += 1

        os.sync()
        log_line(cluster, GREEN, f"random read completed from {remote}, block_size={size_text}, reads={reads}, sync completed")
    except Exception as exc:
        log_line(cluster, RED, f"random read failed from {remote}, block_size={size_text}, reads={reads}, error={exc}")


def random_write(cluster, size_bytes, size_text):
    path = os.path.join(cluster_path(cluster), RAND_FILE)

    try:
        ensure_file(path, 64 * 1024 * 1024)
        file_size = os.path.getsize(path)
        max_offset = max(0, file_size - size_bytes)
        offset = random.randint(0, max_offset)

        fd = os.open(path, os.O_WRONLY)
        try:
            os.lseek(fd, offset, os.SEEK_SET)
            os.write(fd, os.urandom(size_bytes))
            os.fsync(fd)
        finally:
            os.close(fd)

        os.sync()
        log_line(cluster, GREEN, f"random write completed, block_size={size_text}, offset={offset}, fsync completed, sync completed")
    except Exception as exc:
        log_line(cluster, RED, f"random write failed, block_size={size_text}, error={exc}")


# def json_color(value):
#     text = json.dumps(value, separators=(",", ": "))
#
#     text = re.sub(r'("(?:[^"\\]|\\.)*")(?=:)', f"{BLUE}\\1{RESET}", text)
#     text = re.sub(r': ("(?:[^"\\]|\\.)*")', f": {GREEN}\\1{RESET}", text)
#     text = re.sub(r': ([0-9]+)', f": {CYAN}\\1{RESET}", text)
#     text = text.replace(": true", f": {MAGENTA}true{RESET}")
#     text = text.replace(": false", f": {MAGENTA}false{RESET}")
#     text = text.replace(": null", f": {YELLOW}null{RESET}")
#
#     return text


def log_json(cluster, payload):
    prefix = f"{CYAN}{dts()}{RESET} | {color_cluster(cluster)} | "
    pretty_json = json.dumps(payload, indent=4)

    pretty_json = re.sub(r'("(?:[^"\\]|\\.)*")(?=:)', f"{BLUE}\\1{RESET}", pretty_json)
    pretty_json = re.sub(r': ("(?:[^"\\]|\\.)*")', f": {GREEN}\\1{RESET}", pretty_json)
    pretty_json = re.sub(r': ([0-9]+)', f": {CYAN}\\1{RESET}", pretty_json)
    pretty_json = pretty_json.replace(": true", f": {MAGENTA}true{RESET}")
    pretty_json = pretty_json.replace(": false", f": {MAGENTA}false{RESET}")
    pretty_json = pretty_json.replace(": null", f": {YELLOW}null{RESET}")

    lines = pretty_json.splitlines()
    formatted = prefix + lines[0] + "\n"

    for line in lines[1:]:
        formatted += " " * 28 + line + "\n"

    path = log_path(cluster)

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, formatted.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

    os.sync()


def go_crazy_worker(cluster, worker_id, end_time):
    remote = opposite_cluster(cluster)
    local_file = os.path.join(cluster_path(cluster), CRAZY_FILE)
    remote_file = os.path.join(cluster_path(remote), CRAZY_FILE)

    block_size = 47 * 1024
    mid_size = 4 * 1024 * 1024
    large_size = 32 * 1024 * 1024
    seed_size = 512 * 1024 * 1024

    ensure_file(local_file, seed_size)
    ensure_file(remote_file, seed_size)

    stats = {
        "random_reads_47k": 0,
        "random_writes_47k": 0,
        "large_reads_4m": 0,
        "large_writes_4m": 0,
        "large_reads_32m": 0,
        "large_writes_32m": 0,
        "bytes_read": 0,
        "bytes_written": 0,
        "failures": 0,
    }

    last_op = "startup"
    last_offset = 0
    next_report = time.time() + 1

    while time.time() < end_time:
        try:
            action = random.randint(1, 100)

            if action <= 25:
                size = block_size
                file_size = os.path.getsize(remote_file)
                offset = random.randint(0, max(0, file_size - size))

                with open(remote_file, "rb", buffering=0) as handle:
                    handle.seek(offset)
                    handle.read(size)

                stats["random_reads_47k"] += 1
                stats["bytes_read"] += size
                last_op = "remote_random_read_47k"
                last_offset = offset

            elif action <= 65:
                size = block_size
                file_size = os.path.getsize(local_file)
                offset = random.randint(0, max(0, file_size - size))

                fd = os.open(local_file, os.O_WRONLY)
                try:
                    os.lseek(fd, offset, os.SEEK_SET)
                    os.write(fd, os.urandom(size))
                    os.fsync(fd)
                finally:
                    os.close(fd)

                os.sync()
                stats["random_writes_47k"] += 1
                stats["bytes_written"] += size
                last_op = "local_random_write_47k"
                last_offset = offset

            elif action <= 75:
                size = mid_size
                file_size = os.path.getsize(remote_file)
                offset = random.randint(0, max(0, file_size - size))

                with open(remote_file, "rb", buffering=0) as handle:
                    handle.seek(offset)
                    handle.read(size)

                stats["large_reads_4m"] += 1
                stats["bytes_read"] += size
                last_op = "remote_large_read_4m"
                last_offset = offset

            elif action <= 88:
                size = mid_size
                file_size = os.path.getsize(local_file)
                offset = random.randint(0, max(0, file_size - size))

                fd = os.open(local_file, os.O_WRONLY)
                try:
                    os.lseek(fd, offset, os.SEEK_SET)
                    os.write(fd, os.urandom(size))
                    os.fsync(fd)
                finally:
                    os.close(fd)

                os.sync()
                stats["large_writes_4m"] += 1
                stats["bytes_written"] += size
                last_op = "local_large_write_4m"
                last_offset = offset

            elif action <= 93:
                size = large_size
                file_size = os.path.getsize(remote_file)
                offset = random.randint(0, max(0, file_size - size))

                with open(remote_file, "rb", buffering=0) as handle:
                    handle.seek(offset)
                    handle.read(size)

                stats["large_reads_32m"] += 1
                stats["bytes_read"] += size
                last_op = "remote_huge_read_32m"
                last_offset = offset

            else:
                size = large_size
                file_size = os.path.getsize(local_file)
                offset = random.randint(0, max(0, file_size - size))

                fd = os.open(local_file, os.O_WRONLY)
                try:
                    os.lseek(fd, offset, os.SEEK_SET)
                    os.write(fd, os.urandom(size))
                    os.fsync(fd)
                finally:
                    os.close(fd)

                os.sync()
                stats["large_writes_32m"] += 1
                stats["bytes_written"] += size
                last_op = "local_huge_write_32m"
                last_offset = offset

        except Exception as exc:
            stats["failures"] += 1
            last_op = f"failure:{type(exc).__name__}"

        if time.time() >= next_report:
            total_ops = (
                stats["random_reads_47k"]
                + stats["random_writes_47k"]
                + stats["large_reads_4m"]
                + stats["large_writes_4m"]
                + stats["large_reads_32m"]
                + stats["large_writes_32m"]
            )

            payload = {
                "ts": dts(),
                "mode": "go-crazy",
                "cluster": cluster,
                "remote_cluster": remote,
                "worker": worker_id,
                "status": "running",
                "block_size": "47KiB",
                "same_shared_file": True,
                "ops": total_ops,
                "stats": stats,
                "last_op": last_op,
                "last_offset": last_offset,
                "sync": "completed",
            }

            log_json(cluster, payload)
            next_report = time.time() + 1

    total_ops = (
        stats["random_reads_47k"]
        + stats["random_writes_47k"]
        + stats["large_reads_4m"]
        + stats["large_writes_4m"]
        + stats["large_reads_32m"]
        + stats["large_writes_32m"]
    )

    payload = {
        "ts": dts(),
        "mode": "go-crazy",
        "cluster": cluster,
        "remote_cluster": remote,
        "worker": worker_id,
        "status": "finished",
        "ops": total_ops,
        "stats": stats,
        "sync": "completed",
    }

    log_json(cluster, payload)


def go_crazy(duration):
    end_time = time.time() + duration
    workers = []
    workers_per_cluster = 4

    for cluster in CLUSTERS:
        for worker_id in range(1, workers_per_cluster + 1):
            proc = Process(target=go_crazy_worker, args=(cluster, worker_id, end_time))
            proc.start()
            workers.append(proc)

    for proc in workers:
        proc.join()


def build_parser():
    examples = """
Examples:

    Simple heartbeat log only:
        ~/scripts/selab-ds-test.py --simple --duration 300

    Sequential write, 10MB per loop:
        ~/scripts/selab-ds-test.py --sequential-write --size 10MB --duration 300

    Sequential read, 100MB per loop:
        ~/scripts/selab-ds-test.py --sequential-read --size 100MB --duration 300

    Random 4KB reads for 3 seconds per loop:
        ~/scripts/selab-ds-test.py --random-read --size 4KB --duration 300 --read-duration 3

    Random 4KB writes:
        ~/scripts/selab-ds-test.py --random-write --size 4KB --duration 300

    NFSv3 byte-range lock contention:
        ~/scripts/selab-ds-test.py --lock-stress --duration 300

    Full chaos goblin mode:
        ~/scripts/selab-ds-test.py --go-crazy --duration 300

Tail the shared logfile in a second terminal:

    The logfile name is created and printed when the script starts.
    
"""

    parser = argparse.ArgumentParser(
	    description="VAST GNS DataSpace consistency, visibility, and IO stress harness.",
	    epilog=examples,
	    formatter_class=argparse.RawTextHelpFormatter,
	)

    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--simple", action="store_true", help="Write heartbeat messages only")
    modes.add_argument("--sequential-write", action="store_true", help="Sequential write test")
    modes.add_argument("--sequential-read", action="store_true", help="Sequential read test")
    modes.add_argument("--random-read", action="store_true", help="Random read test")
    modes.add_argument("--random-write", action="store_true", help="Random write test")
    modes.add_argument("--go-crazy", action="store_true", help="Mixed simultaneous IO chaos mode")
    modes.add_argument("--lock-stress", action="store_true", help="NFS byte-range lock contention test")

    parser.add_argument("--size", help="IO size, examples: 4KB, 47KiB, 10MB, 1GiB")
    parser.add_argument("--duration", type=int, required=True, help="Runtime in seconds")
    parser.add_argument("--read-duration", type=int, default=3, help="Random read window in seconds")

    return parser


def selected_mode(args):
    if args.simple:
        return "simple"
    if args.sequential_write:
        return "sequential_write"
    if args.sequential_read:
        return "sequential_read"
    if args.random_read:
        return "random_read"
    if args.random_write:
        return "random_write"
    if args.go_crazy:
        return "go_crazy"
    if args.lock_stress:
        return "lock_stress"
    return "unknown"

def lock_stress(cluster):
    remote = opposite_cluster(cluster)
    path = os.path.join(cluster_path(cluster), LOCK_FILE)

    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)

        try:
            start = time.time()

            try:
                fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 1, 0, os.SEEK_SET)
                waited_ms = int((time.time() - start) * 1000)

                marker = f"{dts()} {cluster} acquired byte-range lock while paired with {remote}\n"
                os.lseek(fd, 0, os.SEEK_END)
                os.write(fd, marker.encode("utf-8"))
                os.fsync(fd)
                os.sync()

                time.sleep(0.25)

                fcntl.lockf(fd, fcntl.LOCK_UN, 1, 0, os.SEEK_SET)
                log_line(cluster, GREEN, f"lock acquired and released, byte_range=0:1, waited_ms={waited_ms}, sync completed")

            except BlockingIOError:
                waited_ms = int((time.time() - start) * 1000)
                log_line(cluster, YELLOW, f"lock contention detected, byte_range=0:1, waited_ms={waited_ms}, remote={remote}")

        finally:
            os.close(fd)

    except OSError as exc:
        if exc.errno == 37:
            log_line(
                cluster,
                RED,
                "NFS lock manager unavailable, errno=37, check NLM lockd/statd/rpcbind or nolock mount option",
            )
        else:
            log_line(cluster, RED, f"lock stress failed, errno={exc.errno}, error={exc}")

    except Exception as exc:
        log_line(cluster, RED, f"lock stress failed, error={exc}")
        
def build_dynamic_log_name(mode):
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_mode = mode.replace("_", "-")
    return f"combined_output_log_{safe_mode}_{stamp}.txt"

def run_lock_stress_once():
    workers = []

    for cluster in CLUSTERS:
        proc = Process(target=lock_stress, args=(cluster,))
        proc.start()
        workers.append(proc)

    for proc in workers:
        proc.join()

def create_log_files():
    for cluster in CLUSTERS:
        path = log_path(cluster)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

    os.sync()


def describe_test(mode, size_text, duration, read_duration):
    print("Test about to run:")
    print()

    if mode == "simple":
        print("    Mode:        simple heartbeat")
        print("    Behavior:    write heartbeat log entries only")
    elif mode == "sequential_write":
        print("    Mode:        sequential write")
        print(f"    Behavior:    write {size_text} sequential payloads from each cluster path")
    elif mode == "sequential_read":
        print("    Mode:        sequential read")
        print(f"    Behavior:    read {size_text} sequential payloads from the opposite cluster path")
    elif mode == "random_read":
        print("    Mode:        random read")
        print(f"    Behavior:    read random {size_text} blocks from the opposite cluster path")
        print(f"    Read window: {read_duration}s per loop")
    elif mode == "random_write":
        print("    Mode:        random write")
        print(f"    Behavior:    write random {size_text} blocks from each cluster path")
    elif mode == "lock_stress":
        print("    Mode:        NFSv3 lock stress")
        print("    Behavior:    byte-range lock contention from both cluster paths")
    elif mode == "go_crazy":
        print("    Mode:        go-crazy")
        print("    Behavior:    simultaneous mixed IO from both ends against the same shared file")
        print("    Block mix:   47KiB random IO, 4MiB IO, and 32MiB IO")

    print(f"    Duration:    {duration}s")
    print()


def print_start_banner(mode, size_text, duration, read_duration):
    print()
    print("==============================================================")
    print("      VAST GNS DATASPACE CONSISTENCY + STRESS HARNESS")
    print("==============================================================")
    print()
    print("THIS SCRIPT DOES NOT STREAM TEST OUTPUT TO STDOUT.")
    print()
    describe_test(mode, size_text, duration, read_duration)
    print("The shared logfile has been created and should be visible from either GNS path.")
    print()
    print("OPEN A SECOND TERMINAL WINDOW NOW AND RUN:")
    print()
    print(f"    tail -f /mnt/{CLUSTERS[0]}/dataspace/{OUTFILE}")
    print()
    print("Press Enter after the tail window is running.")
    input("Ready to start the test? ")
    print()
    print("Starting test.")
    print("==============================================================")
    print()

def main():
    global OUTFILE
    parser = build_parser()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    mode = selected_mode(args)

    if mode in ["sequential_write", "sequential_read", "random_read", "random_write"] and not args.size:
        parser.error("--size is required for this test mode")

    size_bytes = parse_size(args.size) if args.size else 0
    size_text = args.size if args.size else "none"

    validate_mounts()

    OUTFILE = build_dynamic_log_name(mode)
    create_log_files()
    print_start_banner(mode, size_text, args.duration, args.read_duration)

    if mode == "go_crazy":
        go_crazy(args.duration)
        print("Test complete.")
        return

    end_time = time.time() + args.duration

    while time.time() < end_time:
        if mode == "lock_stress":
            run_lock_stress_once()
        else:
            for cluster in CLUSTERS:
                if mode == "simple":
                    simple(cluster)
                elif mode == "sequential_write":
                    sequential_write(cluster, size_bytes, size_text)
                elif mode == "sequential_read":
                    sequential_read(cluster, size_bytes, size_text)
                elif mode == "random_read":
                    random_read(cluster, size_bytes, size_text, args.read_duration)
                elif mode == "random_write":
                    random_write(cluster, size_bytes, size_text)

        time.sleep(1)

    print("Test complete.")


if __name__ == "__main__":
    main()
