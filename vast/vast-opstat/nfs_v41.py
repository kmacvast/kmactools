#!/usr/bin/env python3
################################################################################
# Script:      nfs_v41.py
#
# Descr:       NFS v4.1 performance statistics for vast-opstat. Polls VMS
#              instantaneous rates (NFS4Common + NfsMetrics supplement) with
#              metadata proxy panels when native stateful/session counters are
#              unexported by the time-series engine.
#
# Version:     0.1.1
# Author:      KMac
#
# Usage:
#   ./vast-opstat.py --nfs --version=4.1 --vms <VMS_IP>
#
# Controls:
#   Space  - Refresh immediately
#   c      - cNode drill-down
#   v      - View drill-down
#   t      - Tenant drill-down
#   x      - Exit drill-down
#   q      - Quit
################################################################################

import base64
import getpass
import json
import os
import re
import select
import shutil
import signal
import ssl
import sys
import termios
import time
import tty
import urllib.error
import urllib.request
from datetime import datetime

import vast_api_log
from tui_layout import display_width, join_columns, pad_display, format_fixed_number, format_scaled_metric

VERSION = "0.1.1"

DEFAULT_PORT = 443
DEFAULT_USER = "admin"
DEFAULT_REFRESH_SECONDS = 5
DEFAULT_API_TIME_FRAME = "10m"

_NFS4 = "ProtoMetrics,proto_name=NFS4Common"
_NFS_COMMON = "ProtoMetrics,proto_name=NFSCommon"

# NfsMetrics ops queryable on current VMS builds. OPEN/CLOSE/LOCK/LOCKU/SEQUENCE
# are not exported by the time-series engine (confirmed via privileged discovery).
_SUPPLEMENT_DATA_OPS = ("read", "write")
_SUPPLEMENT_META_OPS = ("getattr", "lookup", "create", "remove")

STATEFUL_PANEL_TITLE = "STATEFUL OVERHEAD (VMS Proxies)"
SESSION_PANEL_TITLE = "SESSION WORKLOAD (NFS4Common)"

# NfsMetrics metadata drivers shown when native v4.1 stateful counters are absent.
METADATA_PROXY_OPS = [
    ("getattr", "GETATTR"),
    ("lookup", "LOOKUP"),
    ("create", "CREATE"),
    ("remove", "REMOVE"),
]

# NFS4Common metadata workload profile (session / macro MD view).
SESSION_META_OPS = [
    ("md_iops", "MD IOPS"),
    ("rd_md_iops", "RD MD IOPS"),
    ("wr_md_iops", "WR MD IOPS"),
]

# Data-path operations — NFS4Common instantaneous rates (no delta engine).
DATA_OPS = [
    ("read", "READ"),
    ("write", "WRITE"),
]

_DRILL_CFG = {
    "cnode": {
        "object_type": "cnode",
        "endpoint": "/cnodes/",
        "name_fields": ("name", "hostname", "mgmt_ip"),
    },
    "view": {
        "object_type": "view",
        "endpoint": "/views/",
        "name_fields": ("path", "title", "name"),
    },
    "tenant": {
        "object_type": "tenant",
        "endpoint": "/tenants/",
        "name_fields": ("name",),
    },
}
_MAX_DRILL_OBJECTS = 8

_COL_SEP = "  "
_COL = {"label": 14, "iops": 12, "throughput": 12, "size": 10, "latency": 12}
_DRILL_COL = {"name": 24, "ops": 12, "lat": 10, "bw": 9, "top": 12, "pct": 6}

_ANSI_RE = re.compile(r"\033\[[^m]*m")
_UTF8 = (sys.stdout.encoding or "ascii").lower().startswith("utf")
if _UTF8:
    _H, _V = "─", "│"
    _TL, _TR, _BL, _BR, _LT, _RT = "┌", "┐", "└", "┘", "├", "┤"
    _MUS = "µs"
else:
    _H, _V = "-", "|"
    _TL, _TR, _BL, _BR, _LT, _RT = "+", "+", "+", "+", "+", "+"
    _MUS = "us"

_RST = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_BRED = "\033[1;31m"
_BGREEN = "\033[1;32m"
_BYELLOW = "\033[1;33m"
_BCYAN = "\033[1;36m"
_BWHITE = "\033[1;37m"

_COLOR = False
ARGS = None
VMS = PORT = USER = PASSWORD = None
REFRESH_SECONDS = DEFAULT_REFRESH_SECONDS
API_TIME_FRAME = DEFAULT_API_TIME_FRAME
SAMPLE_AVERAGE_MODE = False
BASE_URL = AUTH = HEADERS = None
SSL_CTX = ssl._create_unverified_context()

CLUSTER_ID = CLUSTER_NAME = None
DATA_MONITOR_ID = META_MONITOR_ID = None
SUPPLEMENT_MONITOR_ID = BW_MONITOR_ID = None
METRICS_SOURCE = "NFS4Common"
LAST_ROWS = {"data": [], "stateful": [], "session": [], "meta": {}}
LAST_SAMPLE = "-"
DRILL_MODE = DRILL_ERROR = None
DRILL_OBJECTS = []
DRILL_MONITORS = []
LAST_DRILL_ROWS = []
ORIGINAL_TERMINAL_SETTINGS = None
KEYBOARD_ENABLED = False


def init_config(args):
    global ARGS, VMS, PORT, USER, PASSWORD, REFRESH_SECONDS, API_TIME_FRAME
    global SAMPLE_AVERAGE_MODE, BASE_URL, AUTH, HEADERS, _COLOR

    ARGS = args
    VMS = args.vms
    PORT = args.port
    USER = args.user
    password = args.password or os.environ.get("VAST_PASSWORD")
    if not password:
        password = getpass.getpass(f"Password for {USER}@{VMS}: ")
    PASSWORD = password
    REFRESH_SECONDS = args.refresh
    SAMPLE_AVERAGE_MODE = bool(args.sample_average)
    API_TIME_FRAME = args.sample_average or DEFAULT_API_TIME_FRAME
    BASE_URL = f"https://{VMS}/api" if PORT == 443 else f"https://{VMS}:{PORT}/api"
    token = os.environ.get("VAST_TOKEN")
    if token:
        AUTH = None
        HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    else:
        AUTH = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        HEADERS = {"Authorization": f"Basic {AUTH}", "Content-Type": "application/json"}
    HEADERS["User-Agent"] = f"vast-opstat/nfs-v41/{VERSION}"
    log_path = vast_api_log.configure(
        getattr(args, "log_api_calls", False), "nfs-v41", VMS, PORT,
    )
    if log_path:
        print(f"API call logging enabled: {log_path}", file=sys.stderr, flush=True)
    _COLOR = sys.stdout.isatty() and not args.no_color


def c(text, code):
    return f"{code}{text}{_RST}" if _COLOR else text


def as_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def raw_bw_to_mb_sec(value):
    bw = as_float(value)
    return bw / 1_000_000.0 if bw is not None else None


def format_throughput_mbs(mbs):
    mbs = as_float(mbs)
    if mbs is None or mbs <= 0:
        return "-", None
    if mbs >= 1024:
        return f"{mbs / 1024:.2f} GB/s", mbs
    if mbs >= 1:
        return f"{mbs:.2f} MB/s", mbs
    return f"{mbs * 1024:.2f} KB/s", mbs


def format_latency_us(us):
    us = as_float(us)
    if us is None or us <= 0:
        return "-", None
    if us >= 1000:
        return f"{us / 1000:.2f} ms", us
    return f"{us:.0f} {_MUS}", us


def format_block_size(value):
    value = as_float(value)
    if value is None or value <= 0:
        return "-", None
    if value >= 1024 ** 2:
        return f"{value / (1024 ** 2):.2f} MB", value
    if value >= 1024:
        return f"{value / 1024:.2f} KB", value
    return f"{value:.0f} B", value


def format_iops(ops):
    ops = as_float(ops)
    if ops is None or ops <= 0:
        return "-"
    if ops >= 100_000:
        return f"{ops:,.0f}"
    if ops >= 100:
        return f"{ops:,.1f}"
    return f"{ops:,.2f}"


def box_top(title, width):
    raw_pre = f"{_TL}{_H} {title} "
    fill = max(0, width - display_width(raw_pre) - 1)
    if _COLOR:
        return c(f"{_TL}{_H} ", _DIM) + c(title, _BWHITE) + c(f" {_H * fill}{_TR}", _DIM)
    return f"{raw_pre}{_H * fill}{_TR}"


def box_bottom(width):
    return c(f"{_BL}{_H * (width - 2)}{_BR}", _DIM)


def box_sep(width):
    return c(f"{_LT}{_H * (width - 2)}{_RT}", _DIM)


def box_row(content, width):
    inner = width - 4
    pad = max(0, inner - display_width(content))
    return f"{c(_V, _DIM)} {content}{' ' * pad} {c(_V, _DIM)}"


def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def api_request(method, path, payload=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=30) as resp:
            body = resp.read().decode()
            elapsed_ms = (time.monotonic() - started) * 1000
            vast_api_log.log_call(method, url, payload, resp.status, body, None, elapsed_ms)
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        elapsed_ms = (time.monotonic() - started) * 1000
        err = f"HTTP {e.code}: {body}"
        vast_api_log.log_call(method, url, payload, e.code, body, err, elapsed_ms)
        raise RuntimeError(f"{method} {url} failed: {err}")


def normalize_list_response(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "objects"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def get_current_cluster():
    data = api_request("GET", "/clusters/")
    clusters = normalize_list_response(data)
    if not clusters:
        raise RuntimeError(f"No clusters returned from /clusters/: {data}")
    cluster = clusters[0]
    if len(clusters) > 1:
        for cl in clusters:
            blob = json.dumps(cl).lower()
            if '"local": true' in blob or '"is_local": true' in blob or '"current": true' in blob:
                cluster = cl
                break
    cluster_id = cluster.get("id")
    cluster_name = (
        cluster.get("name") or cluster.get("cluster_name")
        or cluster.get("mgmt_name") or cluster.get("guid") or "unknown"
    )
    if cluster_id is None:
        raise RuntimeError(f"Cluster record did not include id: {cluster}")
    return cluster_id, cluster_name


def _data_fqn(suffix):
    return f"{_NFS4},{suffix}"


def _nfs_fqn(op, suffix):
    return f"NfsMetrics,nfs_{op}_latency__{suffix}"


def _first_positive(*values):
    """Return the first value > 0; zero is treated as missing for coalesce."""
    for value in values:
        parsed = as_float(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


def _avg_io_from_bw_ops(ops, bw_mbs):
    if not ops or not bw_mbs or ops <= 0:
        return None
    return (bw_mbs * 1_000_000.0) / ops


def build_data_monitor_props():
    """NFS4Common data-path rates — poll values map directly to display (no deltas)."""
    return [
        _data_fqn("rd_iops"), _data_fqn("wr_iops"),
        _data_fqn("rd_bw"), _data_fqn("wr_bw"),
        _data_fqn("read_latency__avg"), _data_fqn("write_latency__avg"),
    ]


def build_supplement_monitor_props():
    """NfsMetrics fallback — active on builds where NFS4Common stays at zero."""
    props = []
    for op in _SUPPLEMENT_DATA_OPS + _SUPPLEMENT_META_OPS:
        props.extend([_nfs_fqn(op, "rate"), _nfs_fqn(op, "avg")])
    return props


def build_bw_monitor_props():
    """Bandwidth from NFSCommon (NFS4Common bw is often zero on mixed NFS clusters)."""
    return [f"{_NFS_COMMON},rd_bw", f"{_NFS_COMMON},wr_bw"]


def build_meta_monitor_props():
    return [
        _data_fqn("md_iops"), _data_fqn("rd_md_iops"), _data_fqn("wr_md_iops"),
        _data_fqn("iops"), _data_fqn("latency"),
    ]


def build_drill_prop_list():
    return (
        build_data_monitor_props()
        + build_supplement_monitor_props()
        + build_bw_monitor_props()
        + build_meta_monitor_props()
    )


def _create_monitor_raw(name_suffix, prop_list, object_type, object_ids):
    base_payload = {
        "name": f"adhoc_vast-opstat_nfs41_{name_suffix}_{int(time.time())}",
        "object_type": object_type,
        "object_ids": object_ids,
        "time_frame": API_TIME_FRAME,
        "aggregation": "avg",
        "query_aggregation": "avg",
        "prop_list": prop_list,
    }
    payload = {**base_payload, "granularity": "auto"}
    try:
        result = api_request("POST", "/monitors/", payload)
    except RuntimeError as e:
        msg = str(e)
        if "Invalid granularity: auto" not in msg and "no such granularity auto" not in msg:
            raise
        result = api_request("POST", "/monitors/", base_payload)
    monitor_id = result.get("id") if isinstance(result, dict) else None
    if not monitor_id:
        raise RuntimeError(f"Monitor create did not return id for {name_suffix}: {result}")
    return monitor_id


def create_monitor(name_suffix, prop_list):
    return _create_monitor_raw(name_suffix, prop_list, "cluster", [CLUSTER_ID])


def delete_monitor(monitor_id):
    if monitor_id is None:
        return
    try:
        api_request("DELETE", f"/monitors/{monitor_id}/")
    except Exception:
        pass


def _result_parts(result):
    prop_list = result.get("prop_list", [])
    data = result.get("data", [])
    prop_idx = {name: idx for idx, name in enumerate(prop_list)}
    return prop_list, data, prop_idx


def _latest_row(result):
    _prop_list, data, prop_idx = _result_parts(result)
    if not data:
        return {}, "-"
    row = data[0]
    sample = row[0] if row else "-"
    values = {}
    for name, idx in prop_idx.items():
        if idx < len(row):
            values[name] = row[idx]
    return values, sample


def _metric(values, suffix):
    return as_float(values.get(_data_fqn(suffix)))


def _supplement_metric(values, op, suffix):
    return as_float(values.get(_nfs_fqn(op, suffix)))


def _op_metrics(nfs4_values, supplement_values, bw_values, op_key):
    if op_key == "read":
        ops = _first_positive(
            _metric(nfs4_values, "rd_iops"),
            _supplement_metric(supplement_values, "read", "rate"),
        )
        avg_us = _first_positive(
            _metric(nfs4_values, "read_latency__avg"),
            _supplement_metric(supplement_values, "read", "avg"),
        )
        bw_mbs = _first_positive(
            raw_bw_to_mb_sec(_metric(nfs4_values, "rd_bw")),
            raw_bw_to_mb_sec(as_float(bw_values.get(f"{_NFS_COMMON},rd_bw"))),
        )
        avg_io = _avg_io_from_bw_ops(ops, bw_mbs)
    else:
        ops = _first_positive(
            _metric(nfs4_values, "wr_iops"),
            _supplement_metric(supplement_values, "write", "rate"),
        )
        avg_us = _first_positive(
            _metric(nfs4_values, "write_latency__avg"),
            _supplement_metric(supplement_values, "write", "avg"),
        )
        bw_mbs = _first_positive(
            raw_bw_to_mb_sec(_metric(nfs4_values, "wr_bw")),
            raw_bw_to_mb_sec(as_float(bw_values.get(f"{_NFS_COMMON},wr_bw"))),
        )
        avg_io = _avg_io_from_bw_ops(ops, bw_mbs)
    return {"ops_sec": ops, "avg_us": avg_us, "bw_mbs": bw_mbs, "avg_io_bytes": avg_io}


def _nfs_op_metrics(values, op_key):
    rate = _supplement_metric(values, op_key, "rate")
    avg = _supplement_metric(values, op_key, "avg")
    return {"ops_sec": rate, "avg_us": avg, "bw_mbs": None, "avg_io_bytes": None}


def _metadata_iops_supplement(supplement_values):
    total = 0.0
    found = False
    for op in _SUPPLEMENT_META_OPS:
        rate = _supplement_metric(supplement_values, op, "rate")
        if rate is not None and rate > 0:
            total += rate
            found = True
    return total if found else None


def _build_stateful_rows(supplement_values):
    """NfsMetrics metadata proxy rows — native OPEN/CLOSE/LOCK/LOCKU are unexported."""
    return _rows_with_pct(
        METADATA_PROXY_OPS,
        lambda k: _nfs_op_metrics(supplement_values, k),
    )


def _build_session_rows(meta):
    """NFS4Common md_iops workload profile (instantaneous rates, no deltas)."""
    def _meta_metric(key):
        val = as_float(meta.get(key))
        return {
            "ops_sec": val if val is not None and val > 0 else None,
            "avg_us": None,
            "bw_mbs": None,
            "avg_io_bytes": None,
        }

    return _rows_with_pct(SESSION_META_OPS, _meta_metric)


def _rows_with_pct(row_defs, metrics_fn):
    rows = []
    for key, label in row_defs:
        m = metrics_fn(key)
        rows.append({"key": key, "label": label, **m})
    total = sum(as_float(r["ops_sec"]) or 0 for r in rows)
    for r in rows:
        ops = as_float(r["ops_sec"]) or 0
        r["pct"] = (ops / total * 100) if total > 0 else None
    return rows


def build_rows_from_results(
    data_result,
    supplement_result=None,
    bw_result=None,
    meta_result=None,
):
    global METRICS_SOURCE
    nfs4_values, sample = _latest_row(data_result)
    supplement_values, _ = _latest_row(supplement_result) if supplement_result else ({}, sample)
    bw_values, _ = _latest_row(bw_result) if bw_result else ({}, sample)
    meta_values, _ = _latest_row(meta_result) if meta_result else ({}, sample)

    data_rows = _rows_with_pct(
        DATA_OPS,
        lambda k: _op_metrics(nfs4_values, supplement_values, bw_values, k),
    )
    nfs4_active = any(
        (as_float(_metric(nfs4_values, s)) or 0) > 0
        for s in ("rd_iops", "wr_iops", "rd_bw", "wr_bw")
    )
    supplement_active = any(
        (as_float(_supplement_metric(supplement_values, op, "rate")) or 0) > 0
        for op in _SUPPLEMENT_DATA_OPS
    )
    if nfs4_active and supplement_active:
        METRICS_SOURCE = "NFS4Common + NfsMetrics"
    elif nfs4_active:
        METRICS_SOURCE = "NFS4Common"
    elif supplement_active:
        METRICS_SOURCE = "NfsMetrics supplement"
    else:
        METRICS_SOURCE = "idle"

    md_iops = _first_positive(
        _metric(meta_values, "md_iops"),
        _metadata_iops_supplement(supplement_values),
    )
    meta = {
        "md_iops": md_iops,
        "rd_md_iops": _metric(meta_values, "rd_md_iops"),
        "wr_md_iops": _metric(meta_values, "wr_md_iops"),
        "total_iops": _first_positive(_metric(meta_values, "iops"), md_iops),
        "latency_us": _first_positive(
            _metric(meta_values, "latency"),
            weighted_latency(data_rows),
        ),
    }
    stateful_rows = _build_stateful_rows(supplement_values)
    session_rows = _build_session_rows(meta)

    return {"data": data_rows, "stateful": stateful_rows, "session": session_rows, "meta": meta}, sample


def weighted_latency(rows):
    pairs = [
        (as_float(r["ops_sec"]), as_float(r["avg_us"]))
        for r in rows if (as_float(r["ops_sec"]) or 0) > 0 and as_float(r["avg_us"]) is not None
    ]
    weight = sum(w for w, _ in pairs)
    if weight <= 0:
        return None
    return sum(w * v for w, v in pairs) / weight


def _dash(w):
    return c(pad_display("-", w, ">"), _DIM)


def _metric_cell(text, w, color):
    return c(format_scaled_metric(text, w), color)


def _label_cell(text, w, color):
    return c(pad_display(text, w, "<"), color)


def _table_header_titles(titles):
    cells = []
    for title, key, align in titles:
        cells.append(c(pad_display(title, _COL[key], align), _BOLD))
    return join_columns(cells, _COL_SEP)


def _data_row_cells(row):
    w = _COL
    ops = as_float(row.get("ops_sec"))
    active = ops is not None and ops > 0
    if not active:
        color = _DIM
        return join_columns([
            _label_cell(row["label"], w["label"], color),
            _dash(w["iops"]), _dash(w["throughput"]), _dash(w["size"]), _dash(w["latency"]),
        ], _COL_SEP)
    bw_text, _ = format_throughput_mbs(row.get("bw_mbs"))
    size_text, _ = format_block_size(row.get("avg_io_bytes"))
    lat_text, lat_us = format_latency_us(row.get("avg_us"))
    label_color = _BCYAN if row["key"] == "read" else _BYELLOW if row["key"] == "write" else _BWHITE
    lat_color = _BRED if (lat_us or 0) > 10_000 else _YELLOW if (lat_us or 0) > 1_000 else _BGREEN
    return join_columns([
        _label_cell(row["label"], w["label"], label_color),
        _metric_cell(format_iops(ops), w["iops"], _GREEN),
        _metric_cell(bw_text, w["throughput"], _CYAN),
        _metric_cell(size_text, w["size"], _CYAN if row["key"] == "read" else _YELLOW),
        _metric_cell(lat_text, w["latency"], lat_color),
    ], _COL_SEP)


def _simple_row_cells(row):
    w = _COL
    ops = as_float(row.get("ops_sec"))
    active = ops is not None and ops > 0
    if not active:
        return join_columns([
            _label_cell(row["label"], w["label"], _DIM),
            _dash(w["iops"]), _dash(w["throughput"]), _dash(w["size"]), _dash(w["latency"]),
        ], _COL_SEP)
    lat_text, lat_us = format_latency_us(row.get("avg_us"))
    lat_color = _BRED if (lat_us or 0) > 10_000 else _YELLOW if (lat_us or 0) > 1_000 else _BGREEN
    return join_columns([
        _label_cell(row["label"], w["label"], _BWHITE),
        _metric_cell(format_iops(ops), w["iops"], _GREEN),
        _dash(w["throughput"]), _dash(w["size"]),
        _metric_cell(lat_text, w["latency"], lat_color),
    ], _COL_SEP)


def _render_data_panel(rows, width):
    titles = [
        ("Operation", "label", "<"), ("IOPS", "iops", ">"), ("Throughput", "throughput", ">"),
        ("Avg Size", "size", ">"), ("Latency", "latency", ">"),
    ]
    print(box_top("DATA OPERATIONS", width))
    print(box_row(_table_header_titles(titles), width))
    print(box_sep(width))
    for row in rows:
        print(box_row(_data_row_cells(row), width))
    print(box_bottom(width))


def _render_stateful_panel(rows, meta, width):
    titles = [
        ("Operation", "label", "<"), ("Ops/s", "iops", ">"), ("", "throughput", ">"),
        ("", "size", ">"), ("Latency", "latency", ">"),
    ]
    print(box_top(STATEFUL_PANEL_TITLE, width))
    print(box_row(_table_header_titles(titles), width))
    print(box_sep(width))
    for row in rows:
        print(box_row(_simple_row_cells(row), width))
    note = (
        "OPEN/CLOSE/LOCK/LOCKU unexported on this VMS — NfsMetrics metadata proxies "
        f"(md_iops {format_iops(meta.get('md_iops'))})"
    )
    print(box_row(c(note, _DIM), width))
    print(box_bottom(width))


def _session_summary_line(meta):
    md = format_iops(meta.get("md_iops"))
    rd = format_iops(meta.get("rd_md_iops"))
    wr = format_iops(meta.get("wr_md_iops"))
    return (
        c("MD IOPS ", _DIM) + c(md, _YELLOW)
        + c("   RD MD ", _DIM) + c(rd, _BCYAN)
        + c("   WR MD ", _DIM) + c(wr, _BYELLOW)
    )


def _render_session_panel(rows, meta, width):
    titles = [
        ("Metric", "label", "<"), ("Ops/s", "iops", ">"), ("", "throughput", ">"),
        ("", "size", ">"), ("Latency", "latency", ">"),
    ]
    print(box_top(SESSION_PANEL_TITLE, width))
    print(box_row(_session_summary_line(meta), width))
    print(box_sep(width))
    print(box_row(_table_header_titles(titles), width))
    print(box_sep(width))
    for row in rows:
        print(box_row(_simple_row_cells(row), width))
    lat_text, _ = format_latency_us(meta.get("latency_us"))
    note = (
        "SEQUENCE unexported on this VMS — NFS4Common metadata workload profile "
        f"(cluster latency {lat_text})"
    )
    print(box_row(c(note, _DIM), width))
    print(box_bottom(width))


def _render_health_panel(snapshot, width):
    data = snapshot["data"]
    meta = snapshot["meta"]
    total_data_iops = sum(as_float(r["ops_sec"]) or 0 for r in data)
    total_bw = sum(as_float(r["bw_mbs"]) or 0 for r in data)
    combined_lat = weighted_latency(data)
    print(box_top("NFS v4.1 HEALTH", width))
    ops_s = c(f"{total_data_iops:,.2f} ops/s" if total_data_iops else "- ops/s", _BWHITE)
    lat_text, _ = format_latency_us(combined_lat)
    lat_s = c(lat_text if combined_lat else "-", _BGREEN if combined_lat else _DIM)
    bw_text, _ = format_throughput_mbs(total_bw)
    bw_s = c(bw_text if total_bw else "-", _CYAN)
    md_s = c(
        f"md {format_iops(meta.get('md_iops'))} ops/s"
        if as_float(meta.get("md_iops")) else "md -",
        _YELLOW,
    )
    print(box_row(f"{ops_s}   Lat {lat_s}   BW {bw_s}   {md_s}", width))
    print(box_bottom(width))


def _obj_name(obj, fields):
    for field in fields:
        val = obj.get(field)
        if val:
            return str(val)
    return str(obj.get("id", "?"))


def _cleanup_drill_monitors():
    global DRILL_MONITORS
    for monitor_id, _name in DRILL_MONITORS:
        delete_monitor(monitor_id)
    DRILL_MONITORS = []


def enter_drill_mode(mode):
    global DRILL_MODE, DRILL_OBJECTS, DRILL_ERROR, LAST_DRILL_ROWS

    cfg = _DRILL_CFG.get(mode)
    if not cfg:
        DRILL_ERROR = f"Unknown drill mode: {mode}"
        return
    try:
        data = api_request("GET", cfg["endpoint"])
        objects = normalize_list_response(data)
    except RuntimeError as e:
        DRILL_ERROR = f"Cannot fetch {mode} objects: {e}"
        return
    if not objects:
        DRILL_ERROR = f"No {mode} objects returned from {cfg['endpoint']}"
        return

    valid = [o for o in objects if "id" in o][:_MAX_DRILL_OBJECTS]
    DRILL_OBJECTS = [
        {"id": o["id"], "name": _obj_name(o, cfg["name_fields"])} for o in valid
    ]
    _cleanup_drill_monitors()
    new_monitors = []
    for obj in DRILL_OBJECTS:
        try:
            monitor_id = _create_monitor_raw(
                f"{mode}_{obj['id']}", build_drill_prop_list(),
                cfg["object_type"], [obj["id"]],
            )
            new_monitors.append((monitor_id, obj["name"]))
        except RuntimeError:
            pass
    if not new_monitors:
        DRILL_ERROR = (
            f"Could not create any {mode} monitors "
            f"(object_type='{cfg['object_type']}' may not be supported)"
        )
        DRILL_OBJECTS = []
        return
    DRILL_MONITORS = new_monitors
    DRILL_MODE = mode
    DRILL_ERROR = None
    LAST_DRILL_ROWS = []


def exit_drill_mode():
    global DRILL_MODE, DRILL_OBJECTS, LAST_DRILL_ROWS, DRILL_ERROR
    _cleanup_drill_monitors()
    DRILL_MODE = None
    DRILL_OBJECTS = []
    LAST_DRILL_ROWS = []
    DRILL_ERROR = None


def fetch_drill_query():
    global LAST_DRILL_ROWS
    drill_rows = []
    for monitor_id, obj_name in DRILL_MONITORS:
        try:
            result = api_request("GET", f"/monitors/{monitor_id}/query/")
            snapshot, _ = build_rows_from_results(result, result, result, result)
            data = snapshot["data"]
            total_ops = sum(as_float(r["ops_sec"]) or 0 for r in data)
            latency = weighted_latency(data)
            total_bw = sum(as_float(r["bw_mbs"]) or 0 for r in data) / 1024.0
            active = [r for r in data if (as_float(r["ops_sec"]) or 0) > 0]
            top = max(active, key=lambda r: as_float(r["ops_sec"]) or 0, default=None)
            drill_rows.append({
                "name": obj_name,
                "total_ops": total_ops,
                "latency_us": latency,
                "bw_gbs": total_bw if total_bw else None,
                "top_rpc": top["label"] if top else "-",
                "top_rpc_pct": as_float(top["pct"]) if top else None,
            })
        except RuntimeError:
            pass
    LAST_DRILL_ROWS = sorted(drill_rows, key=lambda r: r["total_ops"] or 0, reverse=True)


def _render_drill_panel(width):
    dc = _DRILL_COL
    print(box_top(f"{(DRILL_MODE or '?').upper()} DRILL-DOWN", width))
    if DRILL_ERROR:
        print(box_row(c(f"Error: {DRILL_ERROR}", _BRED), width))
        print(box_bottom(width))
        return
    if not LAST_DRILL_ROWS:
        print(box_row(c("Waiting for data…", _DIM), width))
        print(box_bottom(width))
        return
    header = join_columns([
        c(pad_display("Name", dc["name"], "<"), _BOLD),
        c(pad_display("Ops/s", dc["ops"], ">"), _BOLD),
        c(pad_display(f"Avg {_MUS}", dc["lat"], ">"), _BOLD),
        c(pad_display("GB/s", dc["bw"], ">"), _BOLD),
        c(pad_display("Top Op", dc["top"], ">"), _BOLD),
        c(pad_display("Top%", dc["pct"], ">"), _BOLD),
    ], " ")
    print(box_row(header, width))
    print(box_sep(width))
    for dr in LAST_DRILL_ROWS:
        pct = pad_display(f"{(dr.get('top_rpc_pct') or 0):.1f}%", dc["pct"], ">")
        line = join_columns([
            pad_display(dr["name"], dc["name"], "<"),
            c(format_fixed_number(dr["total_ops"], dc["ops"], 2), _BWHITE),
            c(format_fixed_number(dr["latency_us"], dc["lat"], 2), _BGREEN),
            c(format_fixed_number(dr["bw_gbs"], dc["bw"], 3), _CYAN),
            c(pad_display(dr["top_rpc"], dc["top"], ">"), _BWHITE),
            c(pct, _DIM),
        ], " ")
        print(box_row(line, width))
    print(box_sep(width))
    print(box_row(c("Press x to return to cluster view", _DIM), width))
    print(box_bottom(width))


def fetch_monitor_query():
    global LAST_ROWS, LAST_SAMPLE
    data_result = api_request("GET", f"/monitors/{DATA_MONITOR_ID}/query/")
    supplement_result = api_request("GET", f"/monitors/{SUPPLEMENT_MONITOR_ID}/query/")
    bw_result = api_request("GET", f"/monitors/{BW_MONITOR_ID}/query/")
    meta_result = api_request("GET", f"/monitors/{META_MONITOR_ID}/query/")
    LAST_ROWS, LAST_SAMPLE = build_rows_from_results(
        data_result, supplement_result, bw_result, meta_result,
    )


def render_screen():
    width = min(shutil.get_terminal_size((120, 40)).columns, 120)
    clear_screen()
    title = (
        c("  VAST NFS", _BCYAN) + c(" opstat", _BWHITE) + c(f" v{VERSION}", _DIM)
        + f"   VMS {c(f'{VMS}:{PORT}', _BWHITE)}   cluster {c(CLUSTER_NAME, _BWHITE)}"
        + c(f"   refresh {REFRESH_SECONDS}s", _DIM)
    )
    if DRILL_MODE:
        title += c(f"   | {DRILL_MODE.upper()} DRILL", _BYELLOW)
    print(title)
    print(c(f"  sample {LAST_SAMPLE}   frame {API_TIME_FRAME}   source {METRICS_SOURCE}", _DIM))
    print()
    if DRILL_MODE:
        _render_drill_panel(width)
        return
    _render_health_panel(LAST_ROWS, width)
    print()
    _render_data_panel(LAST_ROWS["data"], width)
    print()
    _render_stateful_panel(LAST_ROWS["stateful"], LAST_ROWS["meta"], width)
    print()
    _render_session_panel(LAST_ROWS["session"], LAST_ROWS["meta"], width)
    print()
    print(box_row(
        c("[q]", _BWHITE) + c(" Quit ", _DIM)
        + c("|", _DIM) + c("[c]", _BWHITE) + c(" cNode ", _DIM)
        + c("|", _DIM) + c("[v]", _BWHITE) + c(" View ", _DIM)
        + c("|", _DIM) + c("[t]", _BWHITE) + c(" Tenant ", _DIM)
        + c("|", _DIM) + c("[x]", _BWHITE) + c(" Exit drill ", _DIM)
        + c("|", _DIM) + c("[space]", _BWHITE) + c(" Refresh", _DIM),
        width,
    ), flush=True)


def discover_metrics():
    global CLUSTER_ID, CLUSTER_NAME
    print(f"NFS v4.1 metric discovery — VMS {VMS}:{PORT}\n")
    try:
        CLUSTER_ID, CLUSTER_NAME = get_current_cluster()
        print(f"Cluster: {CLUSTER_NAME} (id={CLUSTER_ID})\n")
    except RuntimeError as e:
        print(f"ERROR: Could not connect to VMS: {e}")
        sys.exit(1)

    print("[ NFS4Common ProtoMetrics (data path — instantaneous rates) ]")
    for suffix in (
        "rd_iops", "wr_iops", "rd_bw", "wr_bw",
        "read_latency__avg", "write_latency__avg",
        "md_iops", "rd_md_iops", "wr_md_iops", "iops", "latency",
    ):
        print(f"  {_data_fqn(suffix)}")

    print("\n[ NfsMetrics supplement (hybrid fallback when NFS4Common is zero) ]")
    for op in _SUPPLEMENT_DATA_OPS + _SUPPLEMENT_META_OPS:
        print(f"  {_nfs_fqn(op, 'rate')} / __avg")
    print("  Data fallback: nfs_{read,write}_latency__rate when NFS4Common IOPS are zero.")

    print("\n[ Bandwidth fallback ]")
    for prop in build_bw_monitor_props():
        print(f"  {prop}")

    print("\n[ Unexported on current VMS builds (not API-permission gated) ]")
    for op in ("open", "close", "lock", "locku", "sequence"):
        print(f"  NfsMetrics,nfs_{op}_latency__rate / __avg — not exported")
    print("  Stateful panel: NfsMetrics proxies (GETATTR, LOOKUP, CREATE, REMOVE)")
    print("  Session panel: NFS4Common md_iops / rd_md_iops / wr_md_iops")

    print("\n[ Drill-down endpoints ]")
    for mode, cfg in _DRILL_CFG.items():
        try:
            objects = normalize_list_response(api_request("GET", cfg["endpoint"]))
            print(f"  {mode:<8} {cfg['endpoint']:<12} {len(objects)} object(s)")
        except RuntimeError as e:
            print(f"  {mode:<8} {cfg['endpoint']:<12} error: {e}")

    print("\nPoll semantics: VMS delivers instantaneous rates (__rate, rd_iops) and")
    print("pre-averaged fields (__avg). No counter-delta engine is used in nfs_v41.")


def setup_keyboard():
    global ORIGINAL_TERMINAL_SETTINGS, KEYBOARD_ENABLED
    if not sys.stdin.isatty():
        KEYBOARD_ENABLED = False
        return
    fd = sys.stdin.fileno()
    ORIGINAL_TERMINAL_SETTINGS = termios.tcgetattr(fd)
    tty.setcbreak(fd)
    KEYBOARD_ENABLED = True


def restore_terminal():
    if ORIGINAL_TERMINAL_SETTINGS and sys.stdin.isatty():
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, ORIGINAL_TERMINAL_SETTINGS)


def check_keypress():
    if not KEYBOARD_ENABLED:
        return ""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return ""


def cleanup():
    restore_terminal()
    delete_monitor(DATA_MONITOR_ID)
    delete_monitor(SUPPLEMENT_MONITOR_ID)
    delete_monitor(BW_MONITOR_ID)
    delete_monitor(META_MONITOR_ID)
    _cleanup_drill_monitors()
    vast_api_log.close()


def signal_handler(_signum, _frame):
    cleanup()
    sys.exit(0)


def main():
    global DATA_MONITOR_ID, META_MONITOR_ID, SUPPLEMENT_MONITOR_ID, BW_MONITOR_ID
    global CLUSTER_ID, CLUSTER_NAME

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    if ARGS.discover_metrics:
        discover_metrics()
        return 0

    setup_keyboard()
    CLUSTER_ID, CLUSTER_NAME = get_current_cluster()
    DATA_MONITOR_ID = create_monitor("data", build_data_monitor_props())
    SUPPLEMENT_MONITOR_ID = create_monitor("supplement", build_supplement_monitor_props())
    BW_MONITOR_ID = create_monitor("bw", build_bw_monitor_props())
    META_MONITOR_ID = create_monitor("meta", build_meta_monitor_props())

    fetch_monitor_query()
    render_screen()
    next_refresh = time.time() + REFRESH_SECONDS

    while True:
        chars = check_keypress()
        if chars:
            if "\x03" in chars or "q" in chars.lower():
                break
            if "c" in chars.lower():
                exit_drill_mode()
                enter_drill_mode("cnode")
                if DRILL_MODE:
                    fetch_drill_query()
            elif "v" in chars.lower():
                exit_drill_mode()
                enter_drill_mode("view")
                if DRILL_MODE:
                    fetch_drill_query()
            elif "t" in chars.lower():
                exit_drill_mode()
                enter_drill_mode("tenant")
                if DRILL_MODE:
                    fetch_drill_query()
            elif "x" in chars.lower():
                exit_drill_mode()
            elif " " in chars:
                fetch_monitor_query()
                if DRILL_MODE:
                    fetch_drill_query()
                next_refresh = time.time() + REFRESH_SECONDS
            render_screen()
            continue

        if time.time() >= next_refresh:
            fetch_monitor_query()
            if DRILL_MODE:
                fetch_drill_query()
            render_screen()
            next_refresh = time.time() + REFRESH_SECONDS
            continue
        time.sleep(0.05)
    return 0


def run(args):
    init_config(args)
    exit_code = 0
    try:
        exit_code = main() or 0
    except KeyboardInterrupt:
        pass
    except Exception as e:
        restore_terminal()
        print(f"ERROR: {e}", file=sys.stderr)
        exit_code = 1
    finally:
        cleanup()
    return exit_code
