# vast-nfstop

Real-time VAST NFS performance monitor for VAST VMS clusters.

Displays live NFS RPC operation statistics with health summaries, workload
classification, latency metrics, throughput, I/O sizing, and delta tracking —
in a curses-like terminal display that refreshes on an interval.

## Credits

This script is based on the original work of **Jeff Mohler (J-Mo)**.

J-Mo built the initial version of `vast-nfstop.py`, a real-time command-line monitoring tool that queries VAST VMS NFS performance counters and displays live NFS RPC operation rates and latency statistics for a VAST cluster. That was the hard part, everything else is just paint.

## Display Layout

Each refresh cycle renders:

![vast-nfstop Screenshot](images/vast-nfstop.png)

https://github.com/kmacvast/kmactools/blob/main/vast/vast-nfstop/images/vast-nfstop.png

## Requirements

- Python 3.8+
- No third-party packages — stdlib only
- VAST VMS accessible over HTTPS (default port 443)
- NFS metrics enabled on the cluster

## Quick Start

```bash
./vast-nfstop.py 10.10.10.10
./vast-nfstop.py --discover-metrics
```

## Usage

```
vast-nfstop.py [VMS_IP] [PORT]
vast-nfstop.py [options]
```

| Option | Default | Description |
|--------|---------|-------------|
| `VMS_IP` | `10.10.10.10` | VMS hostname or IP (positional) |
| `PORT` | `443` | VMS HTTPS port (positional) |
| `--vms HOST` | — | VMS hostname or IP |
| `--port N` | `443` | VMS HTTPS port |
| `--user USER` | `vastadmin` | VMS username |
| `--password PASS` | `vastPassword!` | VMS password |
| `--sample-average WIN` | — | Rolling average window (e.g. `10m`, `1h`, `4h`) |
| `--refresh N` | `5` | Refresh interval in seconds |
| `--csv FILENAME` | — | Append captured samples to a CSV file |
| `--no-color` | — | Disable ANSI color output (for piping/logging) |
| `--discover-metrics` | — | Print available metrics and objects, then exit |
| `--version` | — | Print version and exit |

## Keyboard Controls

| Key | Action |
|-----|--------|
| `Space` | Force immediate refresh |
| `r` | Sort by RPC name (A–Z) |
| `o` | Sort by operations/sec (high→low) |
| `l` | Sort by average latency (high→low) |
| `w` | Sort by % workload (high→low) |
| `c` | Enter cNode drill-down |
| `v` | Enter view/export drill-down |
| `t` | Enter tenant drill-down |
| `x` | Exit drill-down, return to cluster view |
| `q` | Quit |

### Color Coding

| Color | Meaning |
|-------|---------|
| **Bold cyan** | READ ops, header |
| **Bold yellow** | WRITE ops |
| **Bold green** | Healthy latency (<1 ms), positive ops/BW delta |
| **Yellow** | Moderate latency (1–10 ms), >10% workload |
| **Bold red** | High latency (>10 ms), >50% workload |
| **Dim** | Zero/null values, min/max run stats, separators |
| **Cyan** | Read throughput, data consumer |

### Latency Thresholds

| Status | Threshold |
|--------|-----------|
| HEALTHY | < 1,000 µs |
| MODERATE LATENCY | 1,000–5,000 µs |
| ELEVATED LATENCY | 5,000–10,000 µs |
| DEGRADED | 10,000–50,000 µs |
| CRITICAL | > 50,000 µs |

## Workload Classification

The script automatically classifies the observed workload pattern based on
the proportion of read, write, and metadata operations, plus average I/O size:

| Classification | Heuristic |
|----------------|-----------|
| Idle / no load | < 0.5 ops/s total |
| directory traversal | READDIR/READDIRPLUS > 25% of ops |
| namespace churn | CREATE+MKDIR+REMOVE+RMDIR > 30% |
| metadata-heavy | metadata ops ≥ 80% |
| read-heavy | READ > 3× WRITE, I/O ≥ 80% |
| write-heavy | WRITE > 3× READ, I/O ≥ 80% |
| balanced read/write | both I/O types active, I/O ≥ 80% |
| mixed workload | mixed I/O and metadata |

I/O size qualifiers (`small-file` < 8 KiB, `large-block` ≥ 64 KiB) are
prepended to the classification when I/O operations are dominant.

## Drill-Down Mode

Press `c`, `v`, or `t` to break the cluster-aggregate view down by cNode,
view/export, or tenant. The script:

1. Fetches the list of objects from the VMS API.
2. Creates one RPC monitor + one bandwidth monitor per object (up to 8 objects).
3. Refreshes on the normal interval, showing per-object totals sorted by
   total ops/s.
4. Press `x` to exit drill-down and destroy the extra monitors.

> **Note**: Drill-down requires that the VMS supports per-object NFS monitors
> (i.e. `object_type=cnode/view/tenant` in the monitors API). If the VMS does
> not support this, the script will report the error and remain in cluster view.

## CSV Export

With `--csv nfs.csv`, each refresh appends one row per RPC procedure to the
specified file, including timestamps, cluster identity, all metric values, and
run-min/max/mean statistics. If the file is new or empty, the header row is
written automatically. The file is suitable for import into spreadsheet tools
or time-series databases.

## Metric Discovery

```bash
./vast-nfstop.py --discover-metrics
```

This mode:

- Connects to the VMS and identifies the cluster.
- Queries `/api/cnodes/`, `/api/views/`, `/api/tenants/`, `/api/vips/` and
  reports object counts and sample names.
- Creates a temporary NFS RPC monitor, queries its `prop_list`, reports all
  available metric FQNs, then deletes the monitor.
- Reports drill-down availability for each object type.

Use this to verify connectivity and to identify which metrics the VMS version
supports before committing to a monitoring session.

## Architecture

```
parse_args()
    │
    ▼
main()
    ├── get_current_cluster()        → CLUSTER_ID, CLUSTER_NAME
    ├── create_monitor("rpc", ...)   → RPC_MONITOR_ID
    ├── create_monitor("bw",  ...)   → BW_MONITOR_ID
    │
    └── loop every REFRESH_SECONDS
            ├── fetch_monitor_query()
            │       ├── api_request GET /monitors/{id}/query/
            │       ├── build_rows_from_results()
            │       │       ├── build_rpc_rows_from_single_sample()  (default)
            │       │       └── build_rpc_rows_from_sample_average() (--sample-average)
            │       ├── update_run_stats()
            │       └── write_csv_rows()
            │
            ├── fetch_drill_query()  (if drill active)
            │
            └── render_screen()
                    ├── _render_summary_banner()   NFS health + mix + delta
                    ├── _render_insights()         top ops / latency / BW
                    ├── _render_data_section()     READ / WRITE table
                    └── _render_metadata_section() all other RPCs
```

### Key Data Structures

**Row dict** (one per RPC procedure, built by `attach_run_stats`):

```python
{
    "label":        "READ",
    "ops_sec":      1234.56,   # ops/sec (rate metric)
    "avg_us":       412.34,    # average latency in microseconds
    "pct":          72.1,      # % of total cluster ops
    "bw_gbs":       12.345,    # GB/s (READ/WRITE only; None for metadata)
    "avg_io_bytes": 65536,     # average I/O size in bytes (READ/WRITE only)
    "run_min_us":   98.0,      # session minimum latency
    "run_max_us":   4821.0,    # session maximum latency
    "run_mean_us":  389.0,     # session weighted-mean latency
    "bw_min_gbs":   0.001,     # session minimum throughput
    "bw_max_gbs":   18.432,    # session maximum throughput
    "sample":       "2026-06-17T14:23:00Z",
}
```

### API Interaction

The script uses two API monitors per session:

| Monitor | Metrics | Endpoint |
|---------|---------|----------|
| RPC | `NfsMetrics,nfs_{op}_latency__rate` + `__avg` for all 22 procedures | `POST /api/monitors/` then `GET /api/monitors/{id}/query/` |
| Bandwidth | `ProtoMetrics,proto_name=NFSCommon,rd_bw` + `wr_bw` | Same |

Monitors are created at startup with `object_type=cluster` and deleted on exit
(including on SIGINT/SIGTERM). Drill-down modes create additional temporary
monitors per object, also deleted on exit.

### API Assumptions

- VMS responds at `https://{host}[:{port}]/api/` with HTTP Basic Auth.
- `POST /api/monitors/` accepts `object_type`, `object_ids`, `time_frame`,
  `aggregation`, `query_aggregation`, `prop_list`, and optionally `granularity`.
- `GET /api/monitors/{id}/query/` returns `{"prop_list": [...], "data": [[timestamp, ...], ...]}`.
- Metric FQNs follow the pattern `NfsMetrics,nfs_{op}_latency__{rate|avg}`.
- NULL operation uses `NfsMetrics,nfs_null` (no latency suffix).
- Bandwidth uses `ProtoMetrics,proto_name=NFSCommon,{rd_bw|wr_bw}`.
- `/api/clusters/` returns a list with at least one entry containing `id` and `name`.
- Drill-down object endpoints: `/api/cnodes/`, `/api/views/`, `/api/tenants/`.
- Drill-down `object_type` values: `cnode`, `view`, `tenant`.

If any of these assumptions differ in a specific VMS version, `--discover-metrics`
will surface the discrepancy before a monitoring session is started.

## Future Enhancement Recommendations

- **VIP drill-down**: `/api/vips/` is queried in `--discover-metrics` but not
  wired to the `v` key (which is reserved for views). Could add `--drill vip`
  as a CLI flag, or rebind a key.

- **Alert thresholds**: `--alert-latency-us N` flag that writes a line to
  stderr (or a separate log file) whenever weighted average latency exceeds N µs.
  Useful for integration with monitoring pipelines.

- **Auto-pause on high latency**: in DEGRADED/CRITICAL state, pause refresh
  and prompt the user rather than continuing to scroll past the problem.

- **Historical sparklines**: keep a ring buffer of the last N total_ops values
  and render a one-line ASCII sparkline in the header for at-a-glance trends.

- **Multi-cluster support**: `--vms host1,host2` to query multiple VMS
  endpoints and display a combined table.

- **JSON output mode**: `--json` for machine-readable output, compatible with
  Datadog/Prometheus scraping.

- **Per-tenant bandwidth**: if VAST exposes per-tenant bandwidth metrics in a
  future API version, the tenant drill-down could show throughput alongside
  ops/latency.

- **Granularity auto-detection**: currently the script tries `granularity=auto`
  and falls back silently. It could surface the actual granularity in use so
  operators know the metric resolution.
