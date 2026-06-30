#!/usr/bin/env python3
################################################################################
# Script Name: latency_dumper.py
# Description: CSV NFS RPC latency audit tool. Queries the same VMS RPC monitor
#              used by vast-opstat NFS v3, ranks the top five highest procedure
#              latencies every three seconds, and includes the IOPS-weighted
#              protocol average latency for outlier comparison.
#
# Author: KMac kmac@vastdata.com
# Version: 1.1.0
################################################################################

import argparse
import csv
import getpass
import io
import os
import signal
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VAST_OPSTAT_DIR = os.path.join(_REPO_ROOT, "vast", "vast-opstat")
if _VAST_OPSTAT_DIR not in sys.path:
    sys.path.insert(0, _VAST_OPSTAT_DIR)

import nfs_v3  # noqa: E402

DEFAULT_PORT = 443
DEFAULT_USER = "admin"
POLL_SECONDS = 3
TOP_N = 5

CSV_HEADER = [
    "ISO-Timestamp",
    "NFS RPC CALL NAME",
    "Latency us",
    "Average Latency us",
]


def parse_args(argv=None):
    """Parse CLI connection arguments."""
    parser = argparse.ArgumentParser(
        description="Dump top NFS RPC latencies from VMS (vast-opstat NFS v3 metrics path)",
    )
    parser.add_argument("--vms", required=True, help="VMS hostname or IP")
    parser.add_argument(
        "--vms-port",
        dest="port",
        type=int,
        default=DEFAULT_PORT,
        help=f"VMS HTTPS port (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--port",
        dest="port",
        type=int,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--user", default=DEFAULT_USER, help=f"VMS username (default: {DEFAULT_USER})")
    parser.add_argument("--password", default=None, help="VMS password (prompted if omitted)")
    return parser.parse_args(argv)


def build_config(args):
    """Build the config namespace expected by nfs_v3.init_config()."""
    password = args.password or os.environ.get("VAST_PASSWORD")
    if not password:
        password = getpass.getpass(f"Password for {args.user}@{args.vms}: ")
    return SimpleNamespace(
        vms=args.vms,
        port=args.port,
        user=args.user,
        password=password,
        sample_average=None,
        refresh=POLL_SECONDS,
        csv=None,
        no_color=True,
        discover_metrics=False,
        log_api_calls=False,
    )


def output_csv_path(vms, port):
    """Return a unique CSV path under /tmp for this session."""
    safe_vms = "".join(c if c.isalnum() or c in ".-_" else "_" for c in str(vms))
    return os.path.join(
        "/tmp",
        f"vast-opstat-latency-dumper-{safe_vms}-{port}-{os.getpid()}.csv",
    )


def normalize_iso_timestamp(sample):
    """Return an ISO-8601 UTC timestamp string ending in Z."""
    if not sample or sample == "-":
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    text = str(sample).strip()
    if text.endswith("Z"):
        return text
    if "+" in text:
        text = text.split("+", 1)[0]
        return f"{text}Z"
    return f"{text}Z"


def format_latency_us(value):
    """Format latency for CSV (integer microseconds when whole)."""
    lat = nfs_v3.as_float(value)
    if lat is None:
        return None
    rounded = round(lat)
    if abs(lat - rounded) < 0.0005:
        return str(int(rounded))
    return f"{lat:.2f}"


def extract_rpc_rows(rpc_result):
    """Extract RPC rows using the same path as vast-opstat NFS v3."""
    return nfs_v3.build_rpc_rows_from_single_sample(rpc_result)


def protocol_average_latency_us(rows):
    """IOPS-weighted NFSv3 average latency (same math as vast-opstat health panel)."""
    return nfs_v3.compute_combined_avg_latency(rows)


def rank_top_latencies(rows, limit=TOP_N):
    """Match vast-opstat Highest Latency: active ops with non-null avg_us, max first."""
    active_rows = [r for r in rows if (nfs_v3.as_float(r.get("ops_sec")) or 0) > 0]
    active_with_lat = [
        r for r in active_rows if nfs_v3.as_float(r.get("avg_us")) is not None
    ]
    return sorted(
        active_with_lat,
        key=lambda r: nfs_v3.as_float(r["avg_us"]) or 0.0,
        reverse=True,
    )[:limit]


def format_csv_line(fields):
    """Return one quoted CSV record as plain text."""
    buf = io.StringIO()
    csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(fields)
    return buf.getvalue().rstrip("\n")


class CsvDualWriter:
    """Write identical quoted CSV rows to stdout and a /tmp file."""

    def __init__(self, path):
        self.path = path
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file, quoting=csv.QUOTE_ALL)
        self.write_header()

    def write_header(self):
        line = format_csv_line(CSV_HEADER)
        print(line)
        self._writer.writerow(CSV_HEADER)
        self._file.flush()

    def write_row(self, fields):
        line = format_csv_line(fields)
        print(line)
        sys.stdout.flush()
        self._writer.writerow(fields)
        self._file.flush()

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None


def emit_top_rows(writer, top_rows, all_rows, sample_ts):
    """Write top-N RPC latencies plus protocol average latency for comparison."""
    ts = normalize_iso_timestamp(sample_ts)
    avg_lat_text = format_latency_us(protocol_average_latency_us(all_rows))
    if avg_lat_text is None:
        avg_lat_text = ""
    for row in top_rows:
        lat_text = format_latency_us(row.get("avg_us"))
        if lat_text is None:
            continue
        writer.write_row([ts, row["label"], lat_text, avg_lat_text])


def main(argv=None):
    args = parse_args(argv)
    nfs_v3.init_config(build_config(args))
    rpc_monitor_id = None
    csv_writer = None

    def _cleanup(_signum=None, _frame=None):
        if csv_writer is not None:
            csv_writer.close()
        if rpc_monitor_id is not None:
            nfs_v3.delete_monitor(rpc_monitor_id)
        nfs_v3.vast_api_log.close()
        if _signum is not None:
            raise SystemExit(0)

    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    csv_path = output_csv_path(args.vms, args.port)
    csv_writer = CsvDualWriter(csv_path)
    print(f"CSV output file: {csv_path}", file=sys.stderr, flush=True)

    nfs_v3.CLUSTER_ID, _cluster_name = nfs_v3.get_current_cluster()
    rpc_monitor_id = nfs_v3.create_monitor(
        "latency_dumper_rpc",
        nfs_v3.build_rpc_prop_list(),
    )

    try:
        while True:
            rpc_result = nfs_v3.api_request("GET", f"/monitors/{rpc_monitor_id}/query/")
            rows, sample = extract_rpc_rows(rpc_result)
            emit_top_rows(csv_writer, rank_top_latencies(rows), rows, sample)
            time.sleep(POLL_SECONDS)
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
