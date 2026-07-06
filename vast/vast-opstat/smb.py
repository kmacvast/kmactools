#!/usr/bin/env python3
################################################################################
# Script:      smb.py
#
# Descr:       SMB performance statistics for vast-opstat. SMBCommon aggregate
#              panels (Phase 0 var203). Drill-down in Phase 4.
#
# Version:     0.1.2-dev
# Author:      KMac
#
# Usage:
#   ./vast-opstat.py --smb --vms <VMS_IP>
#   ./vast-opstat.py --smb --discover-metrics --vms <VMS_IP>
#
# Controls (planned):
#   Space  - Refresh immediately
#   c      - cNode drill-down
#   v      - View / share drill-down
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
from tui_layout import display_width, format_fixed_number, format_scaled_metric, join_columns, pad_display

VERSION = "0.1.2-dev"

DEFAULT_PORT = 443
DEFAULT_USER = "admin"
DEFAULT_REFRESH_SECONDS = 5
DEFAULT_API_TIME_FRAME = "10m"

_PROTO_SMB = "ProtoMetrics,proto_name=SMB"
_PROTO_SMB_COMMON = "ProtoMetrics,proto_name=SMBCommon"

# Phase 0 var203: SMBCommon is the only live telemetry class; SmbMetrics per-command
# returns HTTP 400 property_error. METRICS_SOURCE labels the active binding.
METRICS_SOURCE = "SMBCommon"
SMB_PER_COMMAND_EXPORTED = False

# NFSv3+SMB interop counters (optional panel when > 0)
_INTEROP_PREFIX = "NfsMetrics,nfs3_smb_interop"

SMB_CMD_CANDIDATES = (
    "read", "write", "create", "close", "query_directory", "query_info",
    "set_info", "ioctl", "lock", "change_notify", "session_setup",
    "tree_connect", "negotiate", "echo", "cancel", "oplock_break",
)

OBJECT_ENDPOINTS = (
    "/cnodes/", "/views/", "/tenants/", "/vips/",
    "/smbclients/", "/smb_clients/", "/clients/", "/client_connections/",
    "/connected_clients/", "/active_clients/", "/hosts/",
)

PROTO_PROBE_PROPS = [
    f"{_PROTO_SMB},iops",
    f"{_PROTO_SMB},bw",
    f"{_PROTO_SMB},latency",
    f"{_PROTO_SMB_COMMON},rd_iops",
    f"{_PROTO_SMB_COMMON},wr_iops",
    f"{_PROTO_SMB_COMMON},rd_bw",
    f"{_PROTO_SMB_COMMON},wr_bw",
    f"{_PROTO_SMB_COMMON},md_iops",
    f"{_PROTO_SMB_COMMON},rd_md_iops",
    f"{_PROTO_SMB_COMMON},wr_md_iops",
]

_DRILL_CFG = {
    "cnode": {
        "label": "CNODE",
        "object_type": "cnode",
        "endpoint": "/cnodes/",
        "name_fields": ("name", "hostname", "mgmt_ip"),
        "no_aggregation": False,
    },
    "view": {
        "label": "VIEW",
        "object_type": "view",
        "endpoint": "/views/",
        "name_fields": ("path", "title", "name"),
        "no_aggregation": True,
    },
    "tenant": {
        "label": "TENANT",
        "object_type": "tenant",
        "endpoint": "/tenants/",
        "name_fields": ("name",),
        "no_aggregation": False,
    },
}

# View/tenant drill scopes use ViewMetrics/TenantMetrics (SMBCommon is cluster/cnode).
_VIEW_READ_IOPS = "ViewMetrics,read_iops__rate"
_VIEW_WRITE_IOPS = "ViewMetrics,write_iops__rate"
_VIEW_READ_MD = "ViewMetrics,read_md_iops__rate"
_VIEW_WRITE_MD = "ViewMetrics,write_md_iops__rate"
_VIEW_READ_LAT = "ViewMetrics,read_latency__avg"
_VIEW_WRITE_LAT = "ViewMetrics,write_latency__avg"
_VIEW_READ_BW = "ViewMetrics,read_bw__rate"
_VIEW_WRITE_BW = "ViewMetrics,write_bw__rate"

_TENANT_READ_IOPS = "TenantMetrics,read_iops__sum"
_TENANT_WRITE_IOPS = "TenantMetrics,write_iops__sum"
_TENANT_READ_MD = "TenantMetrics,read_md_iops__sum"
_TENANT_WRITE_MD = "TenantMetrics,write_md_iops__sum"
_TENANT_READ_BW = "TenantMetrics,read_bw__sum"
_TENANT_WRITE_BW = "TenantMetrics,write_bw__sum"
_TENANT_READ_LAT = "TenantMetrics,read_latency__sum"
_TENANT_WRITE_LAT = "TenantMetrics,write_latency__sum"
_TENANT_READ_CNT = "TenantMetrics,read_iops__num_samples"
_TENANT_WRITE_CNT = "TenantMetrics,write_iops__num_samples"

_MAX_DRILL_OBJECTS = 8
_DRILL_PROBE_LIMIT = 32
_DRILL_COL = {"name": 24, "ops": 12, "lat": 10, "bw": 9, "top": 12, "pct": 6}

HEALTH_PANEL_TITLE = "SMB HEALTH & WORKLOAD"
INSIGHTS_PANEL_TITLE = "PERFORMANCE INSIGHTS"
DATA_PANEL_TITLE = "DATA PATH"
METADATA_PANEL_TITLE = "METADATA & NAMESPACE"
SESSION_PANEL_TITLE = "SESSION & LOCKING"

DATA_OPS = [("read", "READ"), ("write", "WRITE")]
METADATA_OPS = [
    ("md_total", "METADATA"),
    ("rd_md", "RD METADATA"),
    ("wr_md", "WR METADATA"),
]

_COL_SEP = "  "
_COL = {"label": 14, "iops": 12, "throughput": 12, "size": 10, "latency": 12}

_ANSI_RE = re.compile(r"\033\[[^m]*m")
_UTF8 = (sys.stdout.encoding or "ascii").lower().startswith("utf")
if _UTF8:
    _H, _V = "─", "│"
    _TL, _TR, _BL, _BR, _LT, _RT = "┌", "┐", "└", "┘", "├", "┤"
    _MUS = "µs"
    _DOT, _BLK, _SHD = "●", "█", "░"
    _ARR_UP, _ARR_DN, _ARR_EQ = "▲", "▼", "►"
else:
    _H, _V = "-", "|"
    _TL, _TR, _BL, _BR, _LT, _RT = "+", "+", "+", "+", "+", "+"
    _MUS = "us"
    _DOT, _BLK, _SHD = "*", "#", "."
    _ARR_UP, _ARR_DN, _ARR_EQ = "^", "v", ">"

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
HEADLINE_MONITOR_ID = None
CLIENT_SCOPED = False
CLIENT_IPS = []
LAST_ROWS = {}
PREV_ROWS = {}
LAST_SAMPLE = "-"
ORIGINAL_TERMINAL_SETTINGS = None
KEYBOARD_ENABLED = False
DRILL_MODE = None
DRILL_OBJECTS = []
DRILL_MONITORS = []
LAST_DRILL_ROWS = []
DRILL_ERROR = None
DRILL_STATUS = None

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def init_config(args):
    """Initialize module globals from parsed CLI arguments."""
    global ARGS, VMS, PORT, USER, PASSWORD, REFRESH_SECONDS, API_TIME_FRAME
    global SAMPLE_AVERAGE_MODE, BASE_URL, AUTH, HEADERS

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
    HEADERS["User-Agent"] = f"vast-opstat/smb/{VERSION}"
    log_path = vast_api_log.configure(
        getattr(args, "log_api_calls", False), "smb", VMS, PORT,
    )
    if log_path:
        print(f"API call logging enabled: {log_path}", file=sys.stderr, flush=True)
    global _COLOR
    _COLOR = sys.stdout.isatty() and not args.no_color
    configure_client_scope(args)


def configure_client_scope(args):
    """Parse --client/--clients; no-op monitor scoping until Phase 4b."""
    global CLIENT_SCOPED, CLIENT_IPS
    raw = getattr(args, "clients", None)
    if not raw:
        CLIENT_SCOPED = False
        CLIENT_IPS = []
        return
    CLIENT_IPS = [item.strip() for item in raw.split(",") if item.strip()]
    CLIENT_SCOPED = bool(CLIENT_IPS)


def api_request(method, path, payload=None):
    """Issue an authenticated VMS REST request."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(req, context=SSL_CTX, timeout=60) as resp:
            body = resp.read().decode()
            elapsed_ms = (time.monotonic() - started) * 1000
            vast_api_log.log_call(method, url, payload, resp.status, body, None, elapsed_ms)
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        elapsed_ms = (time.monotonic() - started) * 1000
        err = f"HTTP {e.code}: {body}"
        vast_api_log.log_call(method, url, payload, e.code, body, err, elapsed_ms)
        raise RuntimeError(f"{method} {url} failed: {err}") from e


def normalize_list_response(data):
    """Normalize VMS list endpoints to a plain list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "objects"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def get_current_cluster():
    """Return (cluster_id, cluster_name) for the active cluster."""
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


def smb_command_props():
    """Build candidate SmbMetrics property names for discovery probes."""
    props = []
    for cmd in SMB_CMD_CANDIDATES:
        props.extend([
            f"SmbMetrics,smb_{cmd}_latency__rate",
            f"SmbMetrics,smb_{cmd}_latency__avg",
        ])
    return props


def filter_smb_metrics(metrics):
    """Return metrics catalog entries that mention SMB."""
    hits = []
    for entry in metrics if isinstance(metrics, list) else []:
        text = json.dumps(entry) if isinstance(entry, dict) else str(entry)
        if re.search(r"smb|SMB", text):
            hits.append(entry)
    return hits


def probe_monitor(cluster_id, prop_list, label):
    """Create a temporary monitor, query it, delete it; return (status, detail)."""
    payload = {
        "name": f"adhoc_vast-opstat_smb_discover_{label}_{int(time.time())}",
        "object_type": "cluster",
        "object_ids": [cluster_id],
        "time_frame": "10m",
        "prop_list": prop_list,
        "aggregation": "avg",
        "query_aggregation": "avg",
    }
    try:
        created = api_request("POST", "/monitors/", payload)
        monitor_id = created.get("id") if isinstance(created, dict) else None
        if not monitor_id:
            return "create_failed", str(created)[:200]
        result = api_request("GET", f"/monitors/{monitor_id}/query/")
        api_request("DELETE", f"/monitors/{monitor_id}/")
        rows = len(result.get("data", [])) if isinstance(result, dict) else 0
        props_preview = result.get("prop_list", [])[:6] if isinstance(result, dict) else []
        return "ok", f"{rows} rows, props={props_preview}..."
    except RuntimeError as e:
        return "error", str(e)[:200]


def _common_fqn(suffix):
    return f"{_PROTO_SMB_COMMON},{suffix}"


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


def raw_bw_to_gb_sec(value):
    bw = as_float(value)
    return bw / 1_000_000_000.0 if bw is not None else None


def _first_positive(*values):
    for value in values:
        parsed = as_float(value)
        if parsed is not None and parsed > 0:
            return parsed
    return None


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


def fmt_delta(value, precision=2):
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.{precision}f}"


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


def badge(text, color_code):
    return c(f"[ {text} ]", color_code)


def lat_dot(us):
    if us is None:
        return c(_DOT, _DIM)
    if us > 10_000:
        return c(_DOT, _BRED)
    if us > 1_000:
        return c(_DOT, _YELLOW)
    return c(_DOT, _BGREEN)


def delta_arrow(value):
    if value is None or abs(value) < 0.001:
        return c(_ARR_EQ, _DIM)
    return c(_ARR_UP, _BGREEN) if value > 0 else c(_ARR_DN, _YELLOW)


def delta_arrow_lat(value):
    if value is None or abs(value) < 0.01:
        return c(_ARR_EQ, _DIM)
    return c(_ARR_DN, _BGREEN) if value < 0 else c(_ARR_UP, _YELLOW)


def workload_bar(pct, bar_width=22, color=_GREEN):
    filled = max(0, min(bar_width, round((pct or 0) / 100 * bar_width)))
    empty = bar_width - filled
    bar = c(_BLK * filled, color) + c(_SHD * empty, _DIM)
    return f"{bar}  {(pct or 0):4.1f}%"


def build_headline_monitor_props():
    """SMBCommon cluster monitor — instantaneous rates (Phase 0 confirmed)."""
    return [
        _common_fqn("iops"), _common_fqn("bw"),
        _common_fqn("rd_iops"), _common_fqn("wr_iops"),
        _common_fqn("rd_bw"), _common_fqn("wr_bw"),
        _common_fqn("md_iops"), _common_fqn("rd_md_iops"), _common_fqn("wr_md_iops"),
        _common_fqn("read_latency__avg"), _common_fqn("write_latency__avg"),
        _common_fqn("read_size__avg"), _common_fqn("write_size__avg"),
        _common_fqn("rd_latency"),
    ]


def build_drill_prop_list(mode):
    """Scope-aware monitor props for SMB drill-down."""
    if mode == "view":
        return [
            _VIEW_READ_IOPS, _VIEW_WRITE_IOPS,
            _VIEW_READ_MD, _VIEW_WRITE_MD,
            _VIEW_READ_LAT, _VIEW_WRITE_LAT,
            _VIEW_READ_BW, _VIEW_WRITE_BW,
        ]
    if mode == "tenant":
        return [
            _TENANT_READ_IOPS, _TENANT_WRITE_IOPS,
            _TENANT_READ_MD, _TENANT_WRITE_MD,
            _TENANT_READ_BW, _TENANT_WRITE_BW,
            _TENANT_READ_LAT, _TENANT_WRITE_LAT,
            _TENANT_READ_CNT, _TENANT_WRITE_CNT,
        ]
    return build_headline_monitor_props()


def build_drill_rank_prop_list(mode):
    """Minimal props for one-shot batch ranking of view/tenant candidates."""
    if mode == "view":
        return [_VIEW_READ_IOPS, _VIEW_WRITE_IOPS, _VIEW_READ_MD, _VIEW_WRITE_MD]
    if mode == "tenant":
        return [
            _TENANT_READ_IOPS, _TENANT_WRITE_IOPS,
            _TENANT_READ_MD, _TENANT_WRITE_MD,
        ]
    return build_drill_prop_list(mode)


def _is_batch_drill_mode(mode=None):
    mode = mode or DRILL_MODE
    return mode in ("view", "tenant")


def _slice_result_for_object(result, object_id):
    if not isinstance(result, dict):
        return result
    prop_list, data, prop_idx = _result_parts(result)
    oid_idx = prop_idx.get("object_id")
    if oid_idx is None:
        return result
    filtered = [row for row in data if len(row) > oid_idx and row[oid_idx] == object_id]
    return {"prop_list": prop_list, "data": filtered}


def _create_monitor_raw(name_suffix, prop_list, object_type, object_ids, *, no_aggregation=False):
    base_payload = {
        "name": f"adhoc_vast-opstat_smb_{name_suffix}_{int(time.time())}",
        "object_type": object_type,
        "object_ids": object_ids,
        "time_frame": API_TIME_FRAME,
        "prop_list": prop_list,
    }
    if not no_aggregation:
        base_payload["aggregation"] = "avg"
        base_payload["query_aggregation"] = "avg"

    if no_aggregation:
        result = api_request("POST", "/monitors/", base_payload)
    else:
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
    return as_float(values.get(_common_fqn(suffix)))


def weighted_latency(rows):
    pairs = [
        (as_float(r["ops_sec"]), as_float(r["avg_us"]))
        for r in rows
        if (as_float(r["ops_sec"]) or 0) > 0 and as_float(r["avg_us"]) is not None
    ]
    weight = sum(w for w, _ in pairs)
    if weight <= 0:
        return None
    return sum(w * v for w, v in pairs) / weight


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


def build_rows_from_results(headline_result):
    """Map SMBCommon monitor sample to panel rows."""
    global METRICS_SOURCE
    values, sample = _latest_row(headline_result)

    read_ops = _metric(values, "rd_iops")
    write_ops = _metric(values, "wr_iops")
    read_lat = _first_positive(_metric(values, "read_latency__avg"), _metric(values, "rd_latency"))
    write_lat = _metric(values, "write_latency__avg")
    read_bw = raw_bw_to_mb_sec(_metric(values, "rd_bw"))
    write_bw = raw_bw_to_mb_sec(_metric(values, "wr_bw"))
    read_size = _metric(values, "read_size__avg")
    write_size = _metric(values, "write_size__avg")

    md_iops = _metric(values, "md_iops")
    rd_md = _metric(values, "rd_md_iops")
    wr_md = _metric(values, "wr_md_iops")
    total_iops = _first_positive(
        _metric(values, "iops"),
        (read_ops or 0) + (write_ops or 0) + (md_iops or 0) or None,
    )
    total_bw_mbs = _first_positive(
        raw_bw_to_mb_sec(_metric(values, "bw")),
        ((read_bw or 0) + (write_bw or 0)) or None,
    )

    active = any(
        (as_float(v) or 0) > 0
        for v in (read_ops, write_ops, md_iops, total_iops)
    )
    METRICS_SOURCE = "SMBCommon" if active else "idle"

    def _data_metric(key):
        if key == "read":
            return {
                "ops_sec": read_ops, "avg_us": read_lat,
                "bw_mbs": read_bw, "avg_io_bytes": read_size,
            }
        return {
            "ops_sec": write_ops, "avg_us": write_lat,
            "bw_mbs": write_bw, "avg_io_bytes": write_size,
        }

    def _meta_metric(key):
        mapping = {
            "md_total": md_iops,
            "rd_md": rd_md,
            "wr_md": wr_md,
        }
        val = mapping.get(key)
        return {
            "ops_sec": val if val is not None and val > 0 else None,
            "avg_us": None, "bw_mbs": None, "avg_io_bytes": None,
        }

    data_rows = _rows_with_pct(DATA_OPS, _data_metric)
    metadata_rows = _rows_with_pct(METADATA_OPS, _meta_metric)
    meta = {
        "md_iops": md_iops,
        "rd_md_iops": rd_md,
        "wr_md_iops": wr_md,
        "total_iops": total_iops,
        "total_bw_mbs": total_bw_mbs,
        "latency_us": weighted_latency(data_rows),
    }
    return {
        "data": data_rows,
        "metadata": metadata_rows,
        "session": [],
        "meta": meta,
    }, sample


def smb_workload_mix(meta, data_rows):
    """Return (md_pct, read_pct, write_pct) as percentages of total ops."""
    total = as_float(meta.get("total_iops")) or 0
    if total <= 0:
        return 0.0, 0.0, 0.0
    md = as_float(meta.get("md_iops")) or 0
    read_ops = next((as_float(r["ops_sec"]) or 0 for r in data_rows if r["key"] == "read"), 0)
    write_ops = next((as_float(r["ops_sec"]) or 0 for r in data_rows if r["key"] == "write"), 0)
    return md / total * 100, read_ops / total * 100, write_ops / total * 100


def classify_smb_workload(meta, data_rows):
    """Return a human-readable SMB workload description."""
    total = as_float(meta.get("total_iops")) or 0
    if total < 0.5:
        return "Idle / no SMB load"

    md_pct, read_pct, write_pct = smb_workload_mix(meta, data_rows)
    read_io = next((as_float(r.get("avg_io_bytes")) for r in data_rows if r["key"] == "read"), None)
    size_tag = ""
    if read_io:
        if read_io < 8_192:
            size_tag = "small-file "
        elif read_io >= 65_536:
            size_tag = "large-block "

    if md_pct >= 60:
        dom = "write" if write_pct > read_pct else "read"
        return f"{size_tag}metadata-heavy {dom} workload"
    if md_pct >= 40:
        return f"{size_tag}metadata-elevated mixed workload"
    if read_pct > write_pct * 2:
        return f"{size_tag}read-biased SMB workload"
    if write_pct > read_pct * 2:
        return f"{size_tag}write-biased SMB workload"
    if md_pct > 25:
        return f"{size_tag}mixed data + metadata workload"
    return f"{size_tag}balanced SMB workload"


def smb_health_label(total_ops, combined_latency_us):
    if total_ops is None or total_ops < 0.5:
        return "IDLE", _DIM
    if combined_latency_us is None:
        return "LOW LOAD", _BGREEN
    if combined_latency_us > 50_000:
        return "CRITICAL", _BRED
    if combined_latency_us > 10_000:
        return "DEGRADED", _BRED
    if combined_latency_us > 5_000:
        return "ELEVATED LATENCY", _YELLOW
    if combined_latency_us > 1_000:
        return "MODERATE LATENCY", _YELLOW
    if total_ops < 10:
        return "LOW LOAD", _BGREEN
    return "HEALTHY", _BGREEN


def _all_panel_rows(snapshot):
    return snapshot["data"] + snapshot["metadata"]


def compute_deltas(current_rows, prev_rows):
    if not prev_rows or not current_rows:
        return {}
    prev_by_label = {r["label"]: r for r in prev_rows}
    deltas = {}
    for r in current_rows:
        label = r["label"]
        p = prev_by_label.get(label)
        if not p:
            continue
        d = {}
        cur_ops = as_float(r["ops_sec"])
        prev_ops = as_float(p["ops_sec"])
        cur_lat = as_float(r["avg_us"])
        prev_lat = as_float(p["avg_us"])
        cur_bw = as_float(r.get("bw_mbs"))
        prev_bw = as_float(p.get("bw_mbs"))
        if cur_ops is not None and prev_ops is not None:
            d["ops"] = cur_ops - prev_ops
        if cur_lat is not None and prev_lat is not None:
            d["lat"] = cur_lat - prev_lat
        if cur_bw is not None and prev_bw is not None:
            d["bw"] = cur_bw - prev_bw
        if d:
            deltas[label] = d
    return deltas


def cluster_delta_summary(deltas):
    ops_delta = bw_delta = None
    lat_deltas = []
    for label, d in deltas.items():
        if "ops" in d:
            ops_delta = (ops_delta or 0) + d["ops"]
        if "bw" in d:
            bw_delta = (bw_delta or 0) + d["bw"]
        if "lat" in d:
            lat_deltas.append((label, d["lat"]))
    return ops_delta, bw_delta, lat_deltas


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
        return join_columns([
            _label_cell(row["label"], w["label"], _DIM),
            _dash(w["iops"]), _dash(w["throughput"]), _dash(w["size"]), _dash(w["latency"]),
        ], _COL_SEP)
    bw_text, _ = format_throughput_mbs(row.get("bw_mbs"))
    size_text, _ = format_block_size(row.get("avg_io_bytes"))
    lat_text, lat_us = format_latency_us(row.get("avg_us"))
    label_color = _BCYAN if row["key"] == "read" else _BYELLOW
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
        _metric_cell(lat_text, w["latency"], lat_color) if lat_us else _dash(w["latency"]),
    ], _COL_SEP)


def _render_health_panel(snapshot, deltas, width):
    meta = snapshot["meta"]
    data_rows = snapshot["data"]
    total_ops = as_float(meta.get("total_iops")) or 0
    combined_lat = as_float(meta.get("latency_us"))
    total_bw_mbs = as_float(meta.get("total_bw_mbs"))
    md_pct, read_pct, write_pct = smb_workload_mix(meta, data_rows)
    health_lbl, health_color = smb_health_label(total_ops, combined_lat)
    workload_type = classify_smb_workload(meta, data_rows)
    ops_delta, bw_delta, lat_deltas = cluster_delta_summary(deltas)

    print(box_top(HEALTH_PANEL_TITLE, width))
    ops_s = c(f"{total_ops:,.2f} ops/s" if total_ops else "- ops/s", _BWHITE)
    lat_text, _ = format_latency_us(combined_lat)
    lat_s = c(lat_text if combined_lat else "-", _BGREEN if combined_lat else _DIM)
    bw_text, _ = format_throughput_mbs(total_bw_mbs)
    bw_s = c(bw_text if total_bw_mbs else "-", _CYAN)
    status = (
        badge(health_lbl, health_color)
        + "   " + ops_s
        + "   " + lat_dot(combined_lat) + " Lat " + lat_s
        + "   BW " + bw_s
    )
    print(box_row(status, width))
    print(box_row(c("Workload  ", _DIM) + c(workload_type, _YELLOW), width))
    print(box_row(c(f"{'Metadata':<10}", _DIM) + workload_bar(md_pct, 22, _CYAN), width))
    print(box_row(c(f"{'Read':<10}", _DIM) + workload_bar(read_pct, 22, _BGREEN), width))
    print(box_row(c(f"{'Write':<10}", _DIM) + workload_bar(write_pct, 22, _BYELLOW), width))
    if deltas:
        parts = []
        if ops_delta is not None and abs(ops_delta) >= 0.001:
            parts.append(delta_arrow(ops_delta) + " " + c(fmt_delta(ops_delta, 2) + " ops/s", _GREEN))
        if bw_delta is not None and abs(bw_delta) >= 0.001:
            parts.append(delta_arrow(bw_delta) + " " + c(fmt_delta(bw_delta, 2) + " MB/s", _CYAN))
        if lat_deltas:
            worst = max(lat_deltas, key=lambda x: abs(x[1]))
            parts.append(
                delta_arrow_lat(worst[1])
                + " " + c(f"Lat {fmt_delta(worst[1], 1)} {_MUS} [{worst[0]}]", _YELLOW)
            )
        if parts:
            print(box_row(c("Δ  ", _DIM) + "   ".join(parts), width))
    print(box_bottom(width))


def _render_insights_panel(snapshot, deltas, width):
    rows = _all_panel_rows(snapshot)
    active_rows = [r for r in rows if (as_float(r["ops_sec"]) or 0) > 0]
    meta = snapshot["meta"]

    print(box_top(INSIGHTS_PANEL_TITLE, width))

    top_op = max(active_rows, key=lambda r: as_float(r["ops_sec"]) or 0, default=None)
    if top_op:
        pct_v = as_float(top_op["pct"]) or 0
        print(box_row(
            c("Top Contributor  ", _DIM) + c(top_op["label"], _BWHITE)
            + c(f"  {pct_v:.1f}% of ops", _GREEN),
            width,
        ))

    active_with_lat = [r for r in active_rows if as_float(r["avg_us"]) is not None]
    if active_with_lat:
        hi = max(active_with_lat, key=lambda r: as_float(r["avg_us"]) or 0)
        us = as_float(hi["avg_us"])
        print(box_row(
            c("Highest Latency  ", _DIM) + c(hi["label"], _BWHITE)
            + "   " + lat_dot(us) + " " + c(f"{us:.0f} {_MUS}", _YELLOW),
            width,
        ))

    io_rows = [r for r in snapshot["data"] if as_float(r.get("bw_mbs"))]
    if io_rows:
        top_bw = max(io_rows, key=lambda r: as_float(r["bw_mbs"]) or 0)
        bw_text, _ = format_throughput_mbs(top_bw["bw_mbs"])
        size_text, _ = format_block_size(top_bw.get("avg_io_bytes"))
        line = c("Data Consumer    ", _DIM) + c(top_bw["label"], _BCYAN) + c(f"  {bw_text}", _CYAN)
        if size_text != "-":
            line += c(f"  avg I/O {size_text}", _DIM)
        print(box_row(line, width))

    md_ops = as_float(meta.get("md_iops"))
    if md_ops and md_ops > 0:
        total = as_float(meta.get("total_iops")) or 0
        md_pct = (md_ops / total * 100) if total > 0 else 0
        print(box_row(
            c("Metadata Load    ", _DIM) + c(f"{format_iops(md_ops)} ops/s", _YELLOW)
            + c(f"  ({md_pct:.1f}% of total)", _DIM),
            width,
        ))

    if deltas:
        top_d = max(deltas.items(), key=lambda kv: abs(kv[1].get("ops", 0)), default=None)
        if top_d and abs(top_d[1].get("ops", 0)) > 0.1:
            lbl_d, d = top_d
            line = (
                c("Top Δ            ", _DIM) + c(lbl_d, _BWHITE)
                + "   " + delta_arrow(d["ops"]) + " " + c(fmt_delta(d["ops"], 2) + "/s", _GREEN)
            )
            print(box_row(line, width))

    print(box_row(
        c("Observation      ", _DIM) + c(classify_smb_workload(meta, snapshot["data"]), _YELLOW),
        width,
    ))
    print(box_bottom(width))


def _render_data_panel(rows, width):
    titles = [
        ("Operation", "label", "<"), ("Ops/s", "iops", ">"), ("Throughput", "throughput", ">"),
        ("Avg Size", "size", ">"), ("Latency", "latency", ">"),
    ]
    print(box_top(DATA_PANEL_TITLE, width))
    print(box_row(_table_header_titles(titles), width))
    print(box_sep(width))
    for row in rows:
        print(box_row(_data_row_cells(row), width))
    print(box_bottom(width))


def _render_metadata_panel(rows, meta, width):
    titles = [
        ("Operation", "label", "<"), ("Ops/s", "iops", ">"), ("", "throughput", ">"),
        ("", "size", ">"), ("Latency", "latency", ">"),
    ]
    print(box_top(METADATA_PANEL_TITLE, width))
    print(box_row(_table_header_titles(titles), width))
    print(box_sep(width))
    for row in rows:
        print(box_row(_simple_row_cells(row), width))
    note = (
        "SmbMetrics per-command not exported — SMBCommon metadata aggregates "
        f"(md {format_iops(meta.get('md_iops'))} ops/s)"
    )
    print(box_row(c(note, _DIM), width))
    print(box_bottom(width))


def _render_session_panel(width):
    print(box_top(SESSION_PANEL_TITLE, width))
    print(box_row(c("SESSION_SETUP / TREE_CONNECT / LOCK / IOCTL", _DIM), width))
    print(box_row(c("Per-command counters not exported on this VMS build.", _DIM), width))
    print(box_row(c("Use metadata + interop lease metrics for SMB session pain signals.", _DIM), width))
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


def _parse_sample_ts(sample):
    if not sample or sample == "-":
        return None
    try:
        return datetime.fromisoformat(str(sample).replace("Z", "+00:00"))
    except ValueError:
        return None


def _values_from_result(result):
    prop_list, data, prop_idx = _result_parts(result)
    if not data:
        return {}, prop_idx, "-"
    row = data[0]
    sample = row[0] if row else "-"
    values = {}
    for name, idx in prop_idx.items():
        if idx < len(row):
            values[name] = row[idx]
    return values, prop_idx, sample


def _delta_rate_from_samples(result, sum_fqn):
    prop_list, data, prop_idx = _result_parts(result)
    idx = prop_idx.get(sum_fqn)
    if idx is None or len(data) < 2:
        return None
    newest, oldest = data[0], data[-1]
    t_new = _parse_sample_ts(newest[0])
    t_old = _parse_sample_ts(oldest[0])
    if not t_new or not t_old:
        return None
    dt = abs((t_new - t_old).total_seconds())
    if dt <= 0:
        return None
    delta = as_float(newest[idx])
    old = as_float(oldest[idx])
    if delta is None or old is None:
        return None
    return max(delta - old, 0.0) / dt


def _avg_from_sum_count_deltas(result, sum_fqn, count_fqn):
    prop_list, data, prop_idx = _result_parts(result)
    idx_s, idx_c = prop_idx.get(sum_fqn), prop_idx.get(count_fqn)
    if idx_s is None or idx_c is None or len(data) < 2:
        return None
    sum_delta = as_float(data[0][idx_s]) - as_float(data[-1][idx_s])
    cnt_delta = as_float(data[0][idx_c]) - as_float(data[-1][idx_c])
    if sum_delta is None or cnt_delta is None or cnt_delta <= 0:
        return None
    return sum_delta / cnt_delta


def _weighted_us(pairs):
    valid = [(w, v) for w, v in pairs if (w or 0) > 0 and v is not None]
    weight = sum(w for w, _v in valid)
    if weight <= 0:
        return None
    return sum(w * v for w, v in valid) / weight


def _drill_top_op(op_pairs):
    active = [(label, ops) for label, ops in op_pairs if (ops or 0) > 0]
    if not active:
        return "-", None
    top_label, top_ops = max(active, key=lambda item: item[1])
    total = sum(ops for _, ops in active)
    pct = (top_ops / total * 100.0) if total > 0 else None
    return top_label, pct


def _build_cnode_drill_row(result, obj_name):
    snapshot, _sample = build_rows_from_results(result)
    all_rows = snapshot["data"] + snapshot["metadata"]
    meta = snapshot["meta"]
    total_ops = as_float(meta.get("total_iops")) or sum(as_float(r["ops_sec"]) or 0 for r in all_rows)
    latency = as_float(meta.get("latency_us")) or weighted_latency(snapshot["data"])
    bw_mbs = as_float(meta.get("total_bw_mbs"))
    bw_gbs = (bw_mbs / 1024.0) if bw_mbs else None
    active = [r for r in all_rows if (as_float(r["ops_sec"]) or 0) > 0]
    top = max(active, key=lambda r: as_float(r["ops_sec"]) or 0, default=None)
    return {
        "name": obj_name,
        "total_ops": total_ops if total_ops > 0 else None,
        "latency_us": latency,
        "bw_gbs": bw_gbs,
        "top_rpc": top["label"] if top else "-",
        "top_rpc_pct": as_float(top["pct"]) if top else None,
    }


def _build_view_drill_row(result, obj_name):
    values, _prop_idx, _sample = _values_from_result(result)
    read_ops = as_float(values.get(_VIEW_READ_IOPS)) or 0.0
    write_ops = as_float(values.get(_VIEW_WRITE_IOPS)) or 0.0
    read_md = as_float(values.get(_VIEW_READ_MD)) or 0.0
    write_md = as_float(values.get(_VIEW_WRITE_MD)) or 0.0
    total_ops = read_ops + write_ops + read_md + write_md
    latency = _weighted_us([
        (read_ops, as_float(values.get(_VIEW_READ_LAT))),
        (write_ops, as_float(values.get(_VIEW_WRITE_LAT))),
    ])
    read_bw = raw_bw_to_gb_sec(values.get(_VIEW_READ_BW)) or 0.0
    write_bw = raw_bw_to_gb_sec(values.get(_VIEW_WRITE_BW)) or 0.0
    top_rpc, top_pct = _drill_top_op([
        ("READ", read_ops), ("WRITE", write_ops),
        ("RD MD", read_md), ("WR MD", write_md),
    ])
    return {
        "name": obj_name,
        "total_ops": total_ops if total_ops > 0 else None,
        "latency_us": latency,
        "bw_gbs": (read_bw + write_bw) if (read_bw + write_bw) > 0 else None,
        "top_rpc": top_rpc,
        "top_rpc_pct": top_pct,
    }


def _build_tenant_drill_row(result, obj_name):
    read_ops = _delta_rate_from_samples(result, _TENANT_READ_IOPS) or 0.0
    write_ops = _delta_rate_from_samples(result, _TENANT_WRITE_IOPS) or 0.0
    read_md = _delta_rate_from_samples(result, _TENANT_READ_MD) or 0.0
    write_md = _delta_rate_from_samples(result, _TENANT_WRITE_MD) or 0.0
    total_ops = read_ops + write_ops + read_md + write_md
    read_lat = _avg_from_sum_count_deltas(result, _TENANT_READ_LAT, _TENANT_READ_CNT)
    write_lat = _avg_from_sum_count_deltas(result, _TENANT_WRITE_LAT, _TENANT_WRITE_CNT)
    latency = _weighted_us([(read_ops, read_lat), (write_ops, write_lat)])
    read_bw_gbs = raw_bw_to_gb_sec(_delta_rate_from_samples(result, _TENANT_READ_BW)) or 0.0
    write_bw_gbs = raw_bw_to_gb_sec(_delta_rate_from_samples(result, _TENANT_WRITE_BW)) or 0.0
    top_rpc, top_pct = _drill_top_op([
        ("READ", read_ops), ("WRITE", write_ops),
        ("RD MD", read_md), ("WR MD", write_md),
    ])
    return {
        "name": obj_name,
        "total_ops": total_ops if total_ops > 0 else None,
        "latency_us": latency,
        "bw_gbs": (read_bw_gbs + write_bw_gbs) if (read_bw_gbs + write_bw_gbs) > 0 else None,
        "top_rpc": top_rpc,
        "top_rpc_pct": top_pct,
    }


def _build_drill_row(mode, result, obj_name):
    if mode == "view":
        return _build_view_drill_row(result, obj_name)
    if mode == "tenant":
        return _build_tenant_drill_row(result, obj_name)
    return _build_cnode_drill_row(result, obj_name)


def _rank_drill_candidates(mode, objects, cfg):
    """Rank view/tenant candidates with one batch monitor + one query."""
    if not objects:
        return []

    object_ids = [obj["id"] for obj in objects]
    id_to_name = {obj["id"]: _obj_name(obj, cfg["name_fields"]) for obj in objects}
    ranked = []
    rank_monitor_id = None
    try:
        rank_monitor_id = _create_monitor_raw(
            f"rank_{mode}",
            build_drill_rank_prop_list(mode),
            cfg["object_type"],
            object_ids,
            no_aggregation=cfg.get("no_aggregation", False),
        )
        result = api_request("GET", f"/monitors/{rank_monitor_id}/query/")
        for obj_id in object_ids:
            name = id_to_name[obj_id]
            slice_result = _slice_result_for_object(result, obj_id)
            row = _build_drill_row(mode, slice_result, name)
            ranked.append({
                "id": obj_id,
                "name": name,
                "total_ops": as_float(row.get("total_ops")) or 0.0,
            })
    except RuntimeError:
        ranked = [
            {"id": obj["id"], "name": id_to_name[obj["id"]], "total_ops": 0.0}
            for obj in objects
        ]
    finally:
        delete_monitor(rank_monitor_id)

    ranked.sort(key=lambda item: (-item["total_ops"], item["name"].lower()))
    return [{"id": item["id"], "name": item["name"]} for item in ranked[:_MAX_DRILL_OBJECTS]]


def enter_drill_mode(mode):
    global DRILL_MODE, DRILL_OBJECTS, DRILL_MONITORS, DRILL_ERROR, LAST_DRILL_ROWS

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

    all_valid = [o for o in objects if "id" in o]
    if mode in ("view", "tenant"):
        probe_pool = all_valid[:_DRILL_PROBE_LIMIT]
        DRILL_OBJECTS = _rank_drill_candidates(mode, probe_pool, cfg)
    else:
        selected = all_valid[:_MAX_DRILL_OBJECTS]
        DRILL_OBJECTS = [
            {"id": o["id"], "name": _obj_name(o, cfg["name_fields"])}
            for o in selected
        ]

    if not DRILL_OBJECTS:
        DRILL_ERROR = f"No valid {mode} objects available for drill-down"
        return

    _cleanup_drill_monitors()
    prop_list = build_drill_prop_list(mode)
    new_monitors = []
    last_error = None

    if _is_batch_drill_mode(mode):
        try:
            monitor_id = _create_monitor_raw(
                f"{mode}_batch",
                prop_list,
                cfg["object_type"],
                [obj["id"] for obj in DRILL_OBJECTS],
                no_aggregation=cfg.get("no_aggregation", False),
            )
            new_monitors.append((monitor_id, None))
        except RuntimeError as e:
            last_error = str(e)
    else:
        for obj in DRILL_OBJECTS:
            try:
                monitor_id = _create_monitor_raw(
                    f"{mode}_{obj['id']}",
                    prop_list,
                    cfg["object_type"],
                    [obj["id"]],
                    no_aggregation=cfg.get("no_aggregation", False),
                )
                new_monitors.append((monitor_id, obj["name"]))
            except RuntimeError as e:
                last_error = str(e)

    if not new_monitors:
        hint = ""
        if mode == "view":
            hint = " (view monitors require seconds resolution without aggregation)"
        elif mode == "tenant":
            hint = " (tenant scope requires TenantMetrics counters)"
        detail = f": {last_error}" if last_error else ""
        DRILL_ERROR = (
            f"Could not create any {mode} monitors (object_type="
            f"'{cfg['object_type']}' may not be supported){hint}{detail}"
        )
        DRILL_OBJECTS = []
        return

    DRILL_MONITORS = new_monitors
    DRILL_MODE = mode
    DRILL_ERROR = None
    LAST_DRILL_ROWS = []


def exit_drill_mode():
    global DRILL_MODE, DRILL_OBJECTS, LAST_DRILL_ROWS, DRILL_ERROR, DRILL_STATUS
    _cleanup_drill_monitors()
    DRILL_MODE = None
    DRILL_OBJECTS = []
    LAST_DRILL_ROWS = []
    DRILL_ERROR = None
    DRILL_STATUS = None


def fetch_drill_query():
    global LAST_DRILL_ROWS, DRILL_ERROR
    if not DRILL_MODE:
        return
    drill_rows = []
    query_errors = 0

    if _is_batch_drill_mode() and DRILL_MONITORS:
        monitor_id, _name = DRILL_MONITORS[0]
        try:
            result = api_request("GET", f"/monitors/{monitor_id}/query/")
            for obj in DRILL_OBJECTS:
                slice_result = _slice_result_for_object(result, obj["id"])
                drill_rows.append(_build_drill_row(DRILL_MODE, slice_result, obj["name"]))
        except RuntimeError:
            query_errors = len(DRILL_OBJECTS)
    else:
        for monitor_id, obj_name in DRILL_MONITORS:
            try:
                result = api_request("GET", f"/monitors/{monitor_id}/query/")
                drill_rows.append(_build_drill_row(DRILL_MODE, result, obj_name))
            except RuntimeError:
                query_errors += 1

    LAST_DRILL_ROWS = sorted(
        drill_rows,
        key=lambda r: r["total_ops"] or 0,
        reverse=True,
    )
    if not LAST_DRILL_ROWS and query_errors:
        DRILL_ERROR = (
            f"{DRILL_MODE} drill monitors returned no data "
            f"({query_errors}/{len(DRILL_OBJECTS)} queries failed)"
        )


def switch_drill_mode(mode):
    """Enter drill mode with a standby message during monitor setup."""
    global DRILL_STATUS
    cfg = _DRILL_CFG.get(mode, {})
    exit_drill_mode()
    label = cfg.get("label", mode.upper())
    if mode in ("view", "tenant"):
        DRILL_STATUS = f"Ranking {label} drill-down by activity, stand by..."
    else:
        DRILL_STATUS = f"Switching to {label} drill-down, stand by..."
    render_screen()
    try:
        enter_drill_mode(mode)
        if DRILL_MODE:
            fetch_drill_query()
    finally:
        DRILL_STATUS = None


def _render_drill_panel(width):
    dc = _DRILL_COL
    if DRILL_STATUS:
        print(box_top("DRILL-DOWN", width))
        print(box_row(c(DRILL_STATUS, _YELLOW), width))
        print(box_bottom(width))
        return

    mode_label = DRILL_MODE.upper() if DRILL_MODE else "?"
    print(box_top(f"{mode_label} DRILL-DOWN", width))
    if DRILL_ERROR:
        print(box_row(c(f"Error: {DRILL_ERROR}", _BRED), width))
        print(box_row(c("Press x to return to cluster view", _DIM), width))
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
    global LAST_ROWS, LAST_SAMPLE, PREV_ROWS
    result = api_request("GET", f"/monitors/{HEADLINE_MONITOR_ID}/query/")
    PREV_ROWS = _all_panel_rows(LAST_ROWS) if LAST_ROWS else {}
    LAST_ROWS, LAST_SAMPLE = build_rows_from_results(result)


def render_screen():
    width = min(shutil.get_terminal_size((120, 40)).columns, 120)
    clear_screen()
    title = (
        c("  VAST SMB", _BCYAN) + c(" opstat", _BWHITE) + c(f" v{VERSION}", _DIM)
        + f"   VMS {c(f'{VMS}:{PORT}', _BWHITE)}   cluster {c(CLUSTER_NAME or '?', _BWHITE)}"
        + c(f"   refresh {REFRESH_SECONDS}s", _DIM)
    )
    if CLIENT_SCOPED:
        client_note = CLIENT_IPS[0] if len(CLIENT_IPS) == 1 else f"{CLIENT_IPS[0]} (+{len(CLIENT_IPS) - 1})"
        title += c(f"   | clients {client_note} (Phase 4b)", _BYELLOW)
    if DRILL_MODE:
        title += c(f"   | {DRILL_MODE.upper()} DRILL", _BYELLOW)
    print(title)
    frame_note = f"sample-average {API_TIME_FRAME}" if SAMPLE_AVERAGE_MODE else f"frame {API_TIME_FRAME}"
    print(c(f"  sample {LAST_SAMPLE}   {frame_note}   source {METRICS_SOURCE}", _DIM))
    print()

    if DRILL_MODE or DRILL_ERROR or DRILL_STATUS:
        _render_drill_panel(width)
    else:
        deltas = compute_deltas(_all_panel_rows(LAST_ROWS), PREV_ROWS)
        _render_health_panel(LAST_ROWS, deltas, width)
        print()
        _render_insights_panel(LAST_ROWS, deltas, width)
        print()
        _render_data_panel(LAST_ROWS["data"], width)
        print()
        _render_metadata_panel(LAST_ROWS["metadata"], LAST_ROWS["meta"], width)
        print()
        _render_session_panel(width)
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
    fd = sys.stdin.fileno()
    try:
        readable, _w, _e = select.select([fd], [], [], 0)
    except Exception:
        return ""
    if not readable:
        return ""
    try:
        data = os.read(fd, 32)
    except Exception:
        return ""
    return data.decode(errors="ignore") if data else ""


def cleanup():
    restore_terminal()
    delete_monitor(HEADLINE_MONITOR_ID)
    _cleanup_drill_monitors()
    vast_api_log.close()


def signal_handler(_signum, _frame):
    cleanup()
    sys.exit(0)


def discover_metrics(write_report_path=None):
    """Enumerate SMB-related VMS metrics, objects, and monitor probes (read-only)."""
    global CLUSTER_ID, CLUSTER_NAME
    print(f"SMB metric discovery — VMS {VMS}:{PORT}\n")
    try:
        CLUSTER_ID, CLUSTER_NAME = get_current_cluster()
        print(f"Cluster: {CLUSTER_NAME} (id={CLUSTER_ID})\n")
    except RuntimeError as e:
        print(f"ERROR: Could not connect to VMS: {e}")
        sys.exit(1)

    clusters = normalize_list_response(api_request("GET", "/clusters/"))
    protocols = clusters[0].get("protocols", []) if clusters else []
    print(f"Protocols: {protocols}\n")

    report_lines = [
        "# SMB Phase 0 — Live Discovery Results",
        "",
        f"**VMS:** `{VMS}:{PORT}`  ",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ",
        f"**Cluster:** {CLUSTER_NAME} (id={CLUSTER_ID})  ",
        f"**Protocols:** `{protocols}`  ",
        "",
    ]

    print("[ /api/metrics/ — SMB-related entries ]")
    report_lines.append("## Metrics catalog (`GET /api/metrics/`)")
    try:
        metrics = api_request("GET", "/metrics/")
        smb_hits = filter_smb_metrics(metrics)
        print(f"  SMB-related entries: {len(smb_hits)}")
        report_lines.append(f"- SMB-related entries: **{len(smb_hits)}**")
        for entry in smb_hits[:40]:
            line = entry if isinstance(entry, str) else json.dumps(entry)
            print(f"    {line[:120]}")
            report_lines.append(f"  - `{line[:200]}`")
        if len(smb_hits) > 40:
            report_lines.append(f"  - … and {len(smb_hits) - 40} more")
    except RuntimeError as e:
        print(f"  ERROR: {e}")
        report_lines.append(f"- ERROR: `{e}`")

    print("\n[ Object endpoints ]")
    report_lines += [
        "",
        "## Object endpoints",
        "",
        "| Endpoint | Status | Count | Sample fields |",
        "|----------|--------|-------|---------------|",
    ]
    client_endpoints = []
    for endpoint in OBJECT_ENDPOINTS:
        try:
            objects = normalize_list_response(api_request("GET", endpoint))
            sample_keys = list(objects[0].keys())[:8] if objects else []
            print(f"  {endpoint:<22} {len(objects)} object(s)  keys={sample_keys}")
            report_lines.append(f"| `{endpoint}` | OK | {len(objects)} | `{sample_keys}` |")
            if any(token in endpoint for token in ("client", "smb", "host")) and objects:
                client_endpoints.append((endpoint, objects[:3]))
        except RuntimeError as e:
            msg = str(e)
            code = "HTTP error" if "HTTP" in msg else "error"
            print(f"  {endpoint:<22} {code}: {msg[:80]}")
            report_lines.append(f"| `{endpoint}` | {code} | — | `{msg[:120]}` |")

    print("\n[ Drill object types ]")
    for mode, cfg in _DRILL_CFG.items():
        print(f"  {mode:<8} {cfg['object_type']:<8} {cfg['endpoint']}")

    report_lines += ["", "## Client IP scoping (for `--clients` flag design)", ""]
    if client_endpoints:
        for endpoint, samples in client_endpoints:
            report_lines.append(f"### `{endpoint}` sample objects")
            for obj in samples:
                ip_fields = {
                    key: obj[key] for key in obj
                    if re.search(r"ip|addr|host|client|name|guid", key, re.I)
                }
                report_lines.append(
                    f"- id={obj.get('id')} fields={json.dumps(ip_fields)[:300]}"
                )
    else:
        report_lines.append("- No client-specific REST list endpoint confirmed in this run.")
        report_lines.append("- Phase 4b must re-probe after SMB workload is active.")

    print("\n[ Monitor probes ]")
    report_lines += ["", "## Monitor probes", ""]
    for label, props in (
        ("smbcommon_headline", [
            f"{_PROTO_SMB_COMMON},iops", f"{_PROTO_SMB_COMMON},bw",
            f"{_PROTO_SMB_COMMON},rd_iops", f"{_PROTO_SMB_COMMON},wr_iops",
            f"{_PROTO_SMB_COMMON},md_iops", f"{_PROTO_SMB_COMMON},rd_md_iops",
            f"{_PROTO_SMB_COMMON},wr_md_iops",
            f"{_PROTO_SMB_COMMON},read_latency__avg", f"{_PROTO_SMB_COMMON},write_latency__avg",
        ]),
        ("proto_smb_legacy", PROTO_PROBE_PROPS),
        ("smb_cmds_batch1", smb_command_props()[:20]),
        ("smb_cmds_batch2", smb_command_props()[20:40]),
    ):
        status, detail = probe_monitor(CLUSTER_ID, props, label)
        print(f"  {label:<22} {status}: {detail}")
        report_lines.append(f"- **{label}:** `{status}` — {detail}")

    if SMB_PER_COMMAND_EXPORTED is False:
        print("\n  Note: SmbMetrics per-command props are not exported on this build.")
        print("        Phase 2–3 will use SMBCommon aggregate panels (see SMB_PHASE0_RESULTS.md).")
        report_lines.append("")
        report_lines.append(
            "- **SmbMetrics verdict:** not exported — use SMBCommon aggregate proxy panels"
        )

    view_props = [
        "ViewMetrics,read_iops__rate", "ViewMetrics,write_iops__rate",
        "ViewMetrics,read_md_iops__rate", "ViewMetrics,write_md_iops__rate",
    ]
    try:
        views = normalize_list_response(api_request("GET", "/views/"))
        if views:
            payload = {
                "name": f"adhoc_vast-opstat_smb_discover_view_{int(time.time())}",
                "object_type": "view",
                "object_ids": [views[0]["id"]],
                "time_frame": "10m",
                "prop_list": view_props,
            }
            created = api_request("POST", "/monitors/", payload)
            monitor_id = created.get("id")
            api_request("GET", f"/monitors/{monitor_id}/query/")
            api_request("DELETE", f"/monitors/{monitor_id}/")
            print("  view_no_aggregation ok")
            report_lines.append("- **view_no_aggregation:** `ok`")
        else:
            print("  view_no_aggregation skipped (no views)")
            report_lines.append("- **view_no_aggregation:** skipped (no views)")
    except RuntimeError as e:
        print(f"  view_no_aggregation error: {e}")
        report_lines.append(f"- **view_no_aggregation:** `{e}`")

    if CLIENT_SCOPED:
        print(f"\n[ Client scope requested (Phase 4b) ]")
        print(f"  Clients: {', '.join(CLIENT_IPS)} — not yet applied to monitors")

    if write_report_path:
        out_path = write_report_path
        if not os.path.isabs(out_path):
            out_path = os.path.join(_SCRIPT_DIR, out_path)
        with open(out_path, "w", encoding="utf-8") as handle:
            handle.write("\n".join(report_lines) + "\n")
        print(f"\nReport written: {out_path}")

    print("\nDiscovery complete.")
    return 0


def main():
    """Entry point after init_config."""
    global HEADLINE_MONITOR_ID, CLUSTER_ID, CLUSTER_NAME

    if ARGS.discover_metrics:
        return discover_metrics()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    setup_keyboard()
    CLUSTER_ID, CLUSTER_NAME = get_current_cluster()
    HEADLINE_MONITOR_ID = create_monitor("headline", build_headline_monitor_props())

    fetch_monitor_query()
    render_screen()
    next_refresh = time.time() + REFRESH_SECONDS

    while True:
        chars = check_keypress()
        if chars:
            if "\x03" in chars or "q" in chars.lower():
                break
            if "c" in chars.lower():
                switch_drill_mode("cnode")
            elif "v" in chars.lower():
                switch_drill_mode("view")
            elif "t" in chars.lower():
                switch_drill_mode("tenant")
            elif "x" in chars.lower():
                exit_drill_mode()
            elif " " in chars:
                if DRILL_MODE:
                    fetch_drill_query()
                else:
                    fetch_monitor_query()
                next_refresh = time.time() + REFRESH_SECONDS
            render_screen()
            continue

        if time.time() >= next_refresh:
            if DRILL_MODE:
                fetch_drill_query()
            else:
                fetch_monitor_query()
            render_screen()
            next_refresh = time.time() + REFRESH_SECONDS
            continue
        time.sleep(0.05)
    return 0


def run(args):
    """Protocol handler invoked by vast-opstat.py dispatch."""
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
