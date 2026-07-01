# NFS v4.1 — vast-opstat

Live NFS v4.1 performance telemetry from VMS. Unlike NFS v3 (stateless RPC
procedures), v4.1 is session-oriented with compound operations and in-protocol
locking. This module surfaces data-path throughput plus metadata/session panels
when counters are exported by the cluster build.

## Quick Start

```bash
cd vast/vast-opstat

# Live dashboard
./vast-opstat.py --nfs --version=4.1 --vms <VMS_HOST> --user admin

# Metric discovery (recommended before first use)
./vast-opstat.py --nfs --version=4.1 --vms <VMS_HOST> --discover-metrics
```

## CLI

| Flag | Description |
|------|-------------|
| `--nfs --version=4.1` | Enable NFS v4.1 mode (required pair) |
| `--vms HOST` | VMS hostname or IP |
| `--discover-metrics` | Print NFS4Common catalog + drill availability, then exit |
| `--refresh N` | Poll interval (default 5s) |
| `--sample-average WIN` | Rolling monitor window (`10m`, `1h`, …) |
| `--no-color` | Plain ASCII output |

## Dashboard Panels

### 1. Data Operations

Source: `ProtoMetrics,proto_name=NFS4Common`

When NFS4Common counters are zero (common on mixed NFS clusters), vast-opstat
automatically supplements from:

- `NfsMetrics,nfs_{read,write}_latency__rate/__avg` for IOPS and latency
- `ProtoMetrics,proto_name=NFSCommon,rd_bw/wr_bw` for throughput
- Sum of `lookup/getattr/create/remove` NfsMetrics rates for aggregate md_iops

The title bar shows `source NfsMetrics supplement` when the fallback is active.

| Row | Metrics |
|-----|---------|
| READ | `rd_iops`, `rd_bw`, `read_latency__avg`, `read_size__avg` |
| WRITE | `wr_iops`, `wr_bw`, `write_latency__avg`, `write_size__avg` |

Columns: IOPS, throughput (auto-scaled KB/MB/GB/s), average I/O size, latency (µs/ms).

### 2. Stateful Metadata & Locking

Target ops: **OPEN**, **CLOSE**, **LOCK**, **LOCKU** via `NfsMetrics,nfs_{op}_latency__rate/__avg`.

On var203 (and many current builds) these per-op counters are **not exported** — the
panel renders inactive rows and shows aggregate `md_iops` from NFS4Common as a fallback
metadata workload indicator.

### 3. Session Overhead

Target op: **SEQUENCE** via `NfsMetrics,nfs_sequence_latency__*`.

When unavailable, the panel notes cluster-wide `ProtoMetrics,NFS4Common,latency` as a
session-health proxy.

## Counter Semantics

VMS delivers **instantaneous rates** and **pre-averaged** latency/size fields through
monitors — not raw cumulative totals requiring a delta engine:

- `rd_iops` / `wr_iops` — ops/sec rates
- `*_latency__rate` — op rate companion series
- `*_latency__avg` — mean latency (µs) for the sample bucket
- `rd_bw` / `wr_bw` — raw bytes/sec (display converts to MB/s)

## Interactive Keys

| Key | Action |
|-----|--------|
| `c` | cNode drill-down (`GET /cnodes/`) |
| `v` | View drill-down (`GET /views/`) |
| `t` | Tenant drill-down (`GET /tenants/`) |
| `x` | Exit drill-down |
| `space` | Refresh now |
| `q` | Quit |

Drill-down endpoints are path-relative to `BASE_URL` (`/api`) — no `/api/api/` duplication.

## Metric Catalog Summary (var203)

| Class / prefix | Available on var203 |
|----------------|---------------------|
| `ProtoMetrics,proto_name=NFS4Common,*` | Yes — data path + md_iops aggregates |
| `NfsMetrics,nfs_{open,close,lock,locku,sequence}_*` | No — monitor query returns HTTP 400 |
| `Nfs4Metrics` / `Nfs41Metrics` | No dedicated class |

When VAST adds per-op v4.1 counters, `probe_stateful_metrics()` will auto-enable the
stateful monitor and populate OPEN/CLOSE/LOCK/LOCKU/SEQUENCE rows.

## Architecture

```
vast-opstat.py --nfs --version=4.1
        └── nfs_v41.run(args)
                ├── DATA monitor  (NFS4Common read/write)
                ├── META monitor  (md_iops, cluster latency)
                ├── STATEFUL monitor (optional, build-dependent)
                └── drill monitors (per cnode/view/tenant)
```

Implementation: [`nfs_v41.py`](nfs_v41.py)
