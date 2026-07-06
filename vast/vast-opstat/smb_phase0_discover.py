#!/usr/bin/env python3
################################################################################
# Script Name: smb_phase0_discover.py
# Description: Phase 0 READ-ONLY SMB metric discovery for vast-opstat. Probes
#              VMS /api/metrics/, object endpoints, and temporary monitors.
# Author: KMac kmac@vastdata.com
# Version: 0.1.0
################################################################################
"""Run from vast/vast-opstat on a host with ~/.vastconf or explicit --vms creds."""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from vast.common.utils import load_vast_config

DEFAULT_PORT = 443
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
    "ProtoMetrics,proto_name=SMB,iops",
    "ProtoMetrics,proto_name=SMB,bw",
    "ProtoMetrics,proto_name=SMB,latency",
    "ProtoMetrics,proto_name=SMBCommon,rd_iops",
    "ProtoMetrics,proto_name=SMBCommon,wr_iops",
    "ProtoMetrics,proto_name=SMBCommon,rd_bw",
    "ProtoMetrics,proto_name=SMBCommon,wr_bw",
    "ProtoMetrics,proto_name=SMBCommon,md_iops",
    "ProtoMetrics,proto_name=SMBCommon,rd_md_iops",
    "ProtoMetrics,proto_name=SMBCommon,wr_md_iops",
]


def build_headers(conf):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    token = conf.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        import base64
        user = conf.get("user") or conf.get("username") or "admin"
        password = conf.get("password") or ""
        creds = base64.b64encode(f"{user}:{password}".encode()).decode()
        headers["Authorization"] = f"Basic {creds}"
    return headers


def api_request(base_url, headers, method, path, payload=None):
    url = f"{base_url}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None


def normalize_list(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "data", "objects"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def filter_smb_metrics(metrics):
    hits = []
    for entry in metrics if isinstance(metrics, list) else []:
        text = json.dumps(entry) if isinstance(entry, dict) else str(entry)
        if re.search(r"smb|SMB", text):
            hits.append(entry)
    return hits


def probe_monitor(base_url, headers, cluster_id, prop_list, label):
    payload = {
        "name": f"adhoc_smb_phase0_{label}_{int(time.time())}",
        "object_type": "cluster",
        "object_ids": [cluster_id],
        "time_frame": "10m",
        "prop_list": prop_list,
        "aggregation": "avg",
        "query_aggregation": "avg",
    }
    try:
        created = api_request(base_url, headers, "POST", "/monitors/", payload)
        monitor_id = created.get("id") if isinstance(created, dict) else None
        if not monitor_id:
            return "create_failed", str(created)[:200]
        result = api_request(base_url, headers, "GET", f"/monitors/{monitor_id}/query/")
        api_request(base_url, headers, "DELETE", f"/monitors/{monitor_id}/")
        rows = len(result.get("data", [])) if isinstance(result, dict) else 0
        return "ok", f"{rows} rows, props={result.get('prop_list', [])[:6]}..."
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        return "http_error", f"{e.code} {body}"
    except Exception as e:
        return "error", str(e)[:200]


def smb_command_props():
    props = []
    for cmd in SMB_CMD_CANDIDATES:
        props.extend([
            f"SmbMetrics,smb_{cmd}_latency__rate",
            f"SmbMetrics,smb_{cmd}_latency__avg",
        ])
    return props


def main():
    parser = argparse.ArgumentParser(description="SMB Phase 0 VMS metric discovery")
    parser.add_argument("--vms", help="VMS host (overrides ~/.vastconf)")
    parser.add_argument("--vms-port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--user", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--config", default="~/.vastconf")
    parser.add_argument("--output", default="SMB_PHASE0_RESULTS.md",
                        help="Write markdown report to this path (under vast-opstat/)")
    args = parser.parse_args()

    try:
        conf = load_vast_config(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Provide --vms/--user/--password or create ~/.vastconf on the lab host.")
        return 1

    if args.vms:
        conf["vms"] = args.vms
    if args.user:
        conf["user"] = args.user
    if args.password:
        conf["password"] = args.password

    host = conf.get("vms") or conf.get("address") or conf.get("host")
    if not host:
        print("ERROR: No VMS host in config")
        return 1

    port = args.vms_port
    base_url = f"https://{host}:{port}/api" if port != 443 else f"https://{host}/api"
    headers = build_headers(conf)

    lines = [
        "# SMB Phase 0 — Live Discovery Results",
        "",
        f"**VMS:** `{host}:{port}`  ",
        f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}  ",
        "",
    ]

    print(f"SMB Phase 0 discovery — {host}:{port}\n")

    clusters = normalize_list(api_request(base_url, headers, "GET", "/clusters/"))
    if not clusters:
        print("ERROR: No clusters returned")
        return 1
    cluster = clusters[0]
    cluster_id = cluster.get("id")
    cluster_name = cluster.get("name", "?")
    protocols = cluster.get("protocols", [])
    print(f"Cluster: {cluster_name} (id={cluster_id})")
    print(f"Protocols: {protocols}\n")
    lines += [
        f"**Cluster:** {cluster_name} (id={cluster_id})  ",
        f"**Protocols:** `{protocols}`  ",
        "",
    ]

    # Metrics catalog
    print("[ /api/metrics/ — SMB-related entries ]")
    lines.append("## Metrics catalog (`GET /api/metrics/`)")
    try:
        metrics = api_request(base_url, headers, "GET", "/metrics/")
        smb_hits = filter_smb_metrics(metrics)
        print(f"  SMB-related entries: {len(smb_hits)}")
        lines.append(f"- SMB-related entries: **{len(smb_hits)}**")
        for entry in smb_hits[:40]:
            line = entry if isinstance(entry, str) else json.dumps(entry)
            print(f"    {line[:120]}")
            lines.append(f"  - `{line[:200]}`")
        if len(smb_hits) > 40:
            lines.append(f"  - … and {len(smb_hits) - 40} more")
    except Exception as e:
        print(f"  ERROR: {e}")
        lines.append(f"- ERROR: `{e}`")

    # Object endpoints
    print("\n[ Object endpoints ]")
    lines += ["", "## Object endpoints", "", "| Endpoint | Status | Count | Sample fields |", "|----------|--------|-------|---------------|"]
    client_endpoints = []
    for endpoint in OBJECT_ENDPOINTS:
        try:
            objects = normalize_list(api_request(base_url, headers, "GET", endpoint))
            sample_keys = list(objects[0].keys())[:8] if objects else []
            print(f"  {endpoint:<22} {len(objects)} object(s)  keys={sample_keys}")
            lines.append(f"| `{endpoint}` | OK | {len(objects)} | `{sample_keys}` |")
            if any(k in endpoint for k in ("client", "smb", "host")) and objects:
                client_endpoints.append((endpoint, objects[:3]))
        except urllib.error.HTTPError as e:
            print(f"  {endpoint:<22} HTTP {e.code}")
            lines.append(f"| `{endpoint}` | HTTP {e.code} | — | — |")
        except Exception as e:
            print(f"  {endpoint:<22} error: {e}")
            lines.append(f"| `{endpoint}` | error | — | `{e}` |")

    # Client IP scoping research
    lines += ["", "## Client IP scoping (for `--clients` flag design)", ""]
    if client_endpoints:
        for endpoint, samples in client_endpoints:
            lines.append(f"### `{endpoint}` sample objects")
            for obj in samples:
                ip_fields = {k: obj[k] for k in obj if re.search(
                    r"ip|addr|host|client|name|guid", k, re.I
                )}
                lines.append(f"- id={obj.get('id')} fields={json.dumps(ip_fields)[:300]}")
    else:
        lines.append("- No client-specific REST list endpoint confirmed in this run.")
        lines.append("- Phase 4b must re-probe after SMB workload is active.")

    # Monitor probes
    print("\n[ Monitor probes ]")
    lines += ["", "## Monitor probes", ""]
    for label, props in (
        ("proto_smb", PROTO_PROBE_PROPS),
        ("smb_cmds_batch1", smb_command_props()[:20]),
        ("smb_cmds_batch2", smb_command_props()[20:40]),
    ):
        status, detail = probe_monitor(base_url, headers, cluster_id, props, label)
        print(f"  {label:<18} {status}: {detail}")
        lines.append(f"- **{label}:** `{status}` — {detail}")

    # View monitor probe (no aggregation)
    view_props = [
        "ViewMetrics,read_iops__rate", "ViewMetrics,write_iops__rate",
        "ViewMetrics,read_md_iops__rate", "ViewMetrics,write_md_iops__rate",
    ]
    try:
        views = normalize_list(api_request(base_url, headers, "GET", "/views/"))
        if views:
            payload = {
                "name": f"adhoc_smb_phase0_view_{int(time.time())}",
                "object_type": "view",
                "object_ids": [views[0]["id"]],
                "time_frame": "10m",
                "prop_list": view_props,
            }
            created = api_request(base_url, headers, "POST", "/monitors/", payload)
            mid = created.get("id")
            api_request(base_url, headers, "GET", f"/monitors/{mid}/query/")
            api_request(base_url, headers, "DELETE", f"/monitors/{mid}/")
            print("  view_no_aggregation ok")
            lines.append("- **view_no_aggregation:** `ok`")
        else:
            lines.append("- **view_no_aggregation:** skipped (no views)")
    except Exception as e:
        print(f"  view_no_aggregation error: {e}")
        lines.append(f"- **view_no_aggregation:** `{e}`")

    out_path = os.path.join(_SCRIPT_DIR, args.output)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
