# SMB Phase 0 — Live Discovery Results

**VMS:** `var203.selab.vastdata.com:443`  
**Generated:** 2026-07-06 (live run via `./vast-opstat.py --smb --discover-metrics`)  
**Cluster:** selab-var-203 (id=1)  
**Protocols (cluster record):** `['NFSv3', 'NFSv4.1']` — SMB metrics export via `SMBCommon` despite absent SMB protocol flag

---

## Executive Summary

| Finding | Status | Implementation impact |
|---------|--------|-------------------------|
| `ProtoMetrics,proto_name=SMBCommon,*` | ✅ Monitor query OK (60 rows) | **Primary telemetry source** (Phases 2–3) |
| `ProtoMetrics,proto_name=SMB,iops/bw/latency` | ⚠️ Not in query prop_list | Use `SMBCommon,iops/bw/latency` instead |
| `SmbMetrics,smb_{cmd}_latency__*` | ❌ HTTP 400 `property_error` | **No per-command table** — proxy aggregates only |
| View-scoped `ViewMetrics` | ✅ `view_no_aggregation` OK | Share drill (`v`) validated |
| Client REST endpoints | ✅ Swagger paths | `list_smb_client_connections`, `openfilehandles`, `monitoredhosts`, `topn` |
| Drill objects cnode/view/tenant | ✅ | Phase 4 ready |

**Gate:** Phase 0 complete. Phase 2 may proceed with **SMBCommon-only** panels.

---

## Metrics catalog (`GET /api/metrics/`)

- **SMB-related entries:** 57
- **Classes observed:**
  - `ProtoMetrics,proto_name=SMBCommon` — extensive (rd/wr iops/bw, md_iops, latency/size histograms)
  - `NfsMetrics,nfs3_smb_interop_*` — 8 interop counters (mixed NFS+SMB clusters)
  - No `SmbMetrics` class entries in first 40 catalog hits

### Confirmed SMBCommon FQNs (monitor-exportable)

| FQN suffix | Role |
|------------|------|
| `rd_iops`, `wr_iops` | Data-path op rates |
| `rd_bw`, `wr_bw`, `bw` | Throughput |
| `md_iops`, `rd_md_iops`, `wr_md_iops` | Metadata workload |
| `iops` | Aggregate ops |
| `rd_latency`, `read_latency__rate`, `read_latency__avg` | Read latency |
| `write_latency__rate`, `write_latency__avg` | Write latency |
| `read_size__rate`, `write_size__rate`, `read_size__avg`, `write_size__avg` | Avg IO size proxies |

### Not exportable via time-series engine

| Pattern | Probe result |
|---------|--------------|
| `SmbMetrics,smb_read_latency__rate` (batch 1, 10 cmds) | HTTP 400 `metrics not available` |
| `SmbMetrics,smb_*` (batch 2, remaining cmds) | HTTP 400 `metrics not available` |

**Conclusion:** Same gap class as NFS v4.1 OPEN/CLOSE — build **proxy panels** from SMBCommon aggregates; never fabricate per-command rows.

### Optional: NFSv3 SMB interop panel (low priority)

| FQN | Notes |
|-----|-------|
| `NfsMetrics,nfs3_smb_interop_ops` | Cluster/cnode scope |
| `NfsMetrics,nfs3_smb_interop_io_ops` | IO path interop |
| `NfsMetrics,nfs3_smb_interop_triggered_lease_breaks` | Lease-break signal |
| `NfsMetrics,nfs3_smb_interop_*` | nvhash, handles, lease retries |

Show only when interop counters > 0 (mixed-protocol troubleshooting appendix).

---

## Object endpoints

| Endpoint | Status | Count | Sample fields |
|----------|--------|-------|---------------|
| `/cnodes/` | OK | 2 | `id`, `name`, `hostname`, `mgmt_ip`, … |
| `/views/` | OK | 126 | `id`, `name`, `path`, `title`, `alias`, … |
| `/tenants/` | OK | 29 | `id`, `name`, `use_smb_privileged_user`, … |
| `/vips/` | OK | 370 | `id`, `ip`, `vippool`, `cnode` |
| `/hosts/` | OK | 4 | `id`, `name`, `auto`, `loopback` — **not SMB client IPs** |
| `/smbclients/` | HTTP 404 | — | — |
| `/smb_clients/` | HTTP 404 | — | — |
| `/clients/` | HTTP 404 | — | — |
| `/client_connections/` | HTTP 404 | — | — |
| `/connected_clients/` | HTTP 404 | — | — |
| `/active_clients/` | HTTP 404 | — | — |

---

## Monitor probes

| Probe | Status | Detail |
|-------|--------|--------|
| **proto_smb** (SMB + SMBCommon headline props) | `ok` | 60 rows; returned props are **SMBCommon only** (`rd_bw`, `rd_md_iops`, `wr_md_iops`, `wr_iops`, …) |
| **smb_cmds_batch1** (`SmbMetrics` × 10) | `error` | HTTP 400 `property_error` |
| **smb_cmds_batch2** (`SmbMetrics` × 10) | `error` | HTTP 400 `property_error` |
| **view_no_aggregation** (`ViewMetrics` on first view) | `ok` | Per-share drill viable |

### Monitor mixing rules (confirmed)

- `ProtoMetrics,SMBCommon` props coalesce in one cluster monitor ✅
- `SmbMetrics` props cannot be queried — do not mix into live monitors
- View scope: use `ViewMetrics` only (no aggregation on view monitors — NFS v3 lesson applies)

---

## Client IP scoping (`--clients` flag design)

- **No REST list endpoint** on var203 for SMB clients.
- `/hosts/` (4 objects) is block/initiator oriented, not per-SMB-session clients.
- **Phase 4b options:**
  1. Defer until VMS exposes client object API (document in README).
  2. Re-probe with active SMB sessions (metrics catalog may gain `object_types` with `client` after workload).
  3. Optional `h` host drill via `/hosts/` only if fields map to SMB (unlikely on this build).

**Decision:** Keep `--client`/`--clients` argparse stubs; implement scoping only when Phase 0 re-run on SMB-active cluster finds a viable object_type.

---

## Revised TUI metric binding (Phases 2–3)

### Health & Insights (SMBCommon cluster monitor)

```
rd_iops, wr_iops, md_iops, rd_md_iops, wr_md_iops
rd_bw, wr_bw, bw, iops
read_latency__avg, write_latency__avg  (or __rate where avg zero)
```

### DATA PATH panel (2 rows — not 15 commands)

| Display row | Source |
|-------------|--------|
| READ | `rd_iops`, `rd_bw`, `read_latency__avg`, `read_size__avg` |
| WRITE | `wr_iops`, `wr_bw`, `write_latency__avg`, `write_size__avg` |

### METADATA & NAMESPACE panel (aggregate proxy)

| Display row | Source |
|-------------|--------|
| METADATA (total) | `md_iops`, weighted latency proxy |
| RD METADATA | `rd_md_iops` |
| WR METADATA | `wr_md_iops` |

Label footer: `per-command SmbMetrics not exported — SMBCommon aggregates`.

### SESSION & LOCKING panel

Native SESSION_SETUP / TREE_CONNECT / LOCK / IOCTL counters **not available**.  
Show **VMS PROXY** sub-panel with interop lease-break counters if `nfs3_smb_interop_*` > 0; otherwise dimmed placeholder until a future VMS build exports session metrics.

### Workload classifier (aggregate-based)

| Signal | Rule |
|--------|------|
| Idle | `iops` < 0.5/s |
| Metadata-heavy | `md_iops / iops` > 50% |
| Read-biased | `rd_iops > 2 × wr_iops` |
| Write-biased | `wr_iops > 2 × rd_iops` |
| Interop lease pain | `nfs3_smb_interop_triggered_lease_breaks` rate elevated |

---

## Phase 0 checklist

- [x] Metrics catalog SMB entries captured (57)
- [x] SmbMetrics per-command export table — **unexported**
- [x] ProtoMetrics SMBCommon confirmed
- [x] Client REST endpoint — **none on var203**
- [x] View/tenant/cnode monitor scope validated
- [x] Proxy panel gaps documented
