# NFS v4.1 — vast-opstat

Live NFS v4.1 performance telemetry from VMS. Unlike NFS v3 (stateless RPC
procedures), v4.1 is session-oriented with compound operations and in-protocol
locking. This module maps **instantaneous monitor rates** directly to the TUI on
each refresh — no counter-delta engine.

## Quick Start

```bash
cd vast/vast-opstat

# Live dashboard
./vast-opstat.py --nfs --version=4.1 --vms <VMS_HOST> --user admin

# Metric discovery
./vast-opstat.py --nfs --version=4.1 --vms <VMS_HOST> --discover-metrics
```

## CLI

| Flag | Description |
|------|-------------|
| `--nfs --version=4.1` | Enable NFS v4.1 mode (required pair) |
| `--vms HOST` | VMS hostname or IP |
| `--discover-metrics` | Print metric catalog + drill availability, then exit |
| `--refresh N` | Poll interval (default 5s) |
| `--sample-average WIN` | Rolling monitor window (`10m`, `1h`, …) |
| `--no-color` | Plain ASCII output |

## Dashboard Panels

### 1. Data Operations

Primary source: `ProtoMetrics,proto_name=NFS4Common` instantaneous rates.

| Row | Metrics |
|-----|---------|
| READ | `rd_iops`, `rd_bw`, `read_latency__avg` |
| WRITE | `wr_iops`, `wr_bw`, `write_latency__avg` |

Average I/O size is **derived on each poll** as `throughput ÷ IOPS` (KB/MiB).

**Hybrid fallback:** When NFS4Common data counters read zero but the cluster
shows NFS traffic, vast-opstat supplements from:

- `NfsMetrics,nfs_{read,write}_latency__rate/__avg` for IOPS and latency
- `ProtoMetrics,proto_name=NFSCommon,rd_bw/wr_bw` for throughput

The title bar shows `source NfsMetrics supplement` when the fallback is active.

### 2. Stateful Overhead (VMS Proxies)

Native v4.1 counters **OPEN**, **CLOSE**, **LOCK**, **LOCKU** are **not exported**
by the VMS time-series engine on current builds (confirmed via privileged
discovery — not an API-permission issue).

The panel shows NfsMetrics metadata drivers instead:

| Row | Metrics |
|-----|---------|
| GETATTR | `NfsMetrics,nfs_getattr_latency__rate/__avg` |
| LOOKUP | `NfsMetrics,nfs_lookup_latency__rate/__avg` |
| CREATE | `NfsMetrics,nfs_create_latency__rate/__avg` |
| REMOVE | `NfsMetrics,nfs_remove_latency__rate/__avg` |

### 3. Session Workload (NFS4Common)

Native **SEQUENCE** counters are likewise unexported. The session panel displays
the macro metadata workload profile from NFS4Common:

| Metric | Source |
|--------|--------|
| MD IOPS | `ProtoMetrics,proto_name=NFS4Common,md_iops` |
| RD MD IOPS | `ProtoMetrics,proto_name=NFS4Common,rd_md_iops` |
| WR MD IOPS | `ProtoMetrics,proto_name=NFS4Common,wr_md_iops` |

An aggregate summary line (`MD IOPS / RD MD / WR MD`) appears above the table.

## Counter Semantics

VMS delivers **instantaneous rates** and **pre-averaged** fields through monitors:

- `rd_iops` / `wr_iops` — ops/sec rates (mapped directly, no deltas)
- `*_latency__rate` — NfsMetrics op rate companion series
- `*_latency__avg` — mean latency (µs) for the sample bucket
- `rd_bw` / `wr_bw` — raw bytes/sec (display converts to KB/MB/GB/s)

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

## Architecture

```
vast-opstat.py --nfs --version=4.1
        └── nfs_v41.run(args)
                ├── DATA monitor       (NFS4Common read/write)
                ├── SUPPLEMENT monitor (NfsMetrics hybrid fallback)
                ├── BW monitor         (NFSCommon throughput fallback)
                ├── META monitor       (md_iops, rd/wr md, cluster latency)
                └── drill monitors     (per cnode/view/tenant)
```

Implementation: [`nfs_v41.py`](nfs_v41.py)
