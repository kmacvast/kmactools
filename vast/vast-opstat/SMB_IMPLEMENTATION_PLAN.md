# vast-opstat — SMB Protocol Implementation Plan

**Branch:** `feat/vast-opstat-smb`  
**Status:** Planning — awaiting approval before code  
**Tool version target:** 0.1.2 (SMB release)  
**Author:** KMac kmac@vastdata.com

---

## Executive Summary

SMB workloads differ fundamentally from NFS and block:

| Dimension | NFS v3 | NFS v4.1 | NVMe-oTCP | **SMB (target)** |
|-----------|--------|----------|-----------|------------------|
| Primary unit | Stateless RPC | Session + compounds | LBA I/O | **Session + tree + file handle** |
| Pain signal | READDIR / LOOKUP storms | Stateful proxies | Fabric/reclaim | **QUERY_DIR, CREATE/CLOSE, lease breaks** |
| Client model | Mount + inode | Client ID | Host NQN | **Windows/macOS session + share** |
| Metadata weight | High (RPC table) | Proxy panel | Low | **Dominant in real deployments** |
| Drill `v` key | View path | View path | **VIP** | **View / share path** |

The SMB module must answer the SE question: *"Is the customer slow on data, metadata, connection setup, or locking — and where (cluster, share, tenant, cNode)?"* within one terminal screen.

---

## Phase 0 — Metric Discovery & Design Gate (READ-ONLY)

**Goal:** Confirm what VMS actually exports before locking UI layout.  
**Operation class:** Read-only (`GET /api/metrics/`, `POST /api/monitors/`, `--discover-metrics`).  
**Approval checkpoint:** ☐ You sign off on metric inventory + panel wireframe.

### 0.1 Live VMS discovery (var203 or customer lab)

Run against a cluster with active SMB workload:

```bash
./vast-opstat.py --smb --vms <HOST> --discover-metrics --log-api-calls
```

Probe candidates (hypothesis — must be validated):

| Layer | Expected FQN pattern | Purpose |
|-------|---------------------|---------|
| Aggregate | `ProtoMetrics,proto_name=SMB,iops/bw/latency` | Cluster headline |
| Common | `ProtoMetrics,proto_name=SMBCommon,rd_iops/wr_iops/rd_bw/wr_bw/md_iops` | Data + MD rates (NFS4Common analogue) |
| Per-command | `SmbMetrics,smb_{cmd}_latency__rate/__avg` | Command table (NfsMetrics analogue) |
| View scope | `ViewMetrics,*` with SMB traffic | Per-share drill |
| Tenant scope | `TenantMetrics,*` | Per-tenant drill |

SMB commands to map (priority order for troubleshooting):

| Priority | SMB2/3 command | Typical customer symptom |
|----------|----------------|--------------------------|
| P0 | READ, WRITE | Slow throughput, large/small file |
| P0 | CREATE, CLOSE | Open/close storm, app startup |
| P0 | QUERY_DIRECTORY | Explorer slowness, `dir` hangs |
| P0 | QUERY_INFO, SET_INFO | ACL/attribute churn |
| P1 | IOCTL | Lease break, compression, offload |
| P1 | LOCK | Application file locking |
| P1 | CHANGE_NOTIFY | Directory watch overhead |
| P2 | SESSION_SETUP, TREE_CONNECT, NEGOTIATE | Login/mount storms, reconnect loops |
| P2 | ECHO, CANCEL | Keepalive / timeout behavior |

### 0.2 Discovery deliverables

- [ ] `discover-metrics` output captured to log
- [ ] Table: exported vs unexported commands (like NFS v4.1 OPEN/CLOSE gap)
- [ ] `object_type` matrix: cluster, view, tenant, cnode, vip, smbclient (if exists)
- [ ] Monitor mixing rules documented (ProtoMetrics vs SmbMetrics in same monitor?)
- [ ] View monitor aggregation constraints (NFS v3 lesson: views may reject aggregation)

### 0.3 Proxy panel decision

If native counters are missing (expected for some session/oplock metrics), define **VMS proxy rows** exactly as NFS v4.1 does — never fabricate data.

| If unexported | Proxy candidate |
|---------------|-----------------|
| OPLOCK_BREAK / LEASE_BREAK | IOCTL or LOCK rates |
| SESSION_SETUP | TREE_CONNECT + NEGOTIATE rates |
| CHANGE_NOTIFY | QUERY_DIRECTORY correlation |

**Gate rule:** Phase 1 does not start until Phase 0 inventory is attached to this doc.

---

## Proposed TUI Layout — Screen Blocks & Flow

Design principle: **top = health verdict, middle = where to look, bottom = command evidence.**

```
┌─────────────────────────────────────────────────────────────────────────┐
│  VAST SMB opstat v0.1.2   VMS host:443   cluster   refresh 5s          │
│  mode:latest  frame:10m  sort:ops  sample:2026-07-06T…                  │
└─────────────────────────────────────────────────────────────────────────┘

┌─ SMB HEALTH & WORKLOAD ─────────────────────────────────────────────────┐
│  STATUS: HEALTHY │ Total 12.4K ops/s │ Lat 840 µs │ 2.1 GB/s           │
│  Workload: metadata-heavy small-file read-biased                        │
│  Mix: [Read 22%][Write 8%][Metadata 58%][Session 9%][Lock/IOCTL 3%]    │
│  Δ: ops +420  bw +0.12 GB/s  worst-lat: QUERY_DIRECTORY +2.1 ms        │
└─────────────────────────────────────────────────────────────────────────┘

┌─ PERFORMANCE INSIGHTS ──────────────────────────────────────────────────┐
│  Top Contributor: QUERY_DIRECTORY (41%)                                 │
│  Highest Latency: CREATE (4.2 ms)                                       │
│  Data Consumer:   READ avg 128 KB                                       │
│  Top Δ Mover:     CLOSE (+180 ops/s)                                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─ DATA PATH ─────────────────────────────────────────────────────────────┐
│  Command   Ops/s      Throughput   Avg Size   Latency                   │
│  READ      2,840      1.62 GB/s    592 KB     620 µs                    │
│  WRITE     1,020      0.48 GB/s    472 KB     1.1 ms                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─ METADATA & NAMESPACE ──────────────────────────────────────────────────┐
│  CREATE          1,240 ops/s    3.8 ms                                    │
│  CLOSE           1,180 ops/s    1.2 ms                                    │
│  QUERY_DIRECTORY   890 ops/s    4.2 ms   ← Explorer pain                 │
│  QUERY_INFO        420 ops/s    2.1 ms                                    │
│  SET_INFO          180 ops/s    1.8 ms                                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─ SESSION & LOCKING ─────────────────────────────────────────────────────┐
│  SESSION_SETUP      45 ops/s    12 ms   (or VMS PROXY panel)             │
│  TREE_CONNECT       38 ops/s     8 ms                                    │
│  LOCK               22 ops/s     0.9 ms                                  │
│  IOCTL              15 ops/s     2.4 ms   (lease/offload proxy)          │
│  CHANGE_NOTIFY       8 ops/s     1.1 ms                                  │
└─────────────────────────────────────────────────────────────────────────┘

 Footer: c=cNode  v=View/Share  t=Tenant  x=exit drill  Space=refresh  q=quit
```

### Why this block order

1. **Health first** — immediate answer: idle, healthy, degraded, metadata-dominated.
2. **Insights second** — narrows investigation before reading 15 command rows.
3. **Data path third** — separates "slow reads/writes" from metadata (most SMB tickets blame wrong layer).
4. **Metadata fourth** — SMB-specific root cause for Windows/macOS UX pain.
5. **Session & locking last** — connection storms and lease issues are less common but high severity.

### Workload classifier (SMB-specific rules)

| Condition | Label |
|-----------|-------|
| Total ops < 0.5/s | Idle / no SMB load |
| SESSION_SETUP+TREE_CONNECT > 25% | connection / mount storm |
| QUERY_DIRECTORY+QUERY_INFO > 35% | directory enumeration heavy |
| CREATE+CLOSE > 40% | open/close churn (app pattern) |
| LOCK+IOCTL > 15% | locking / lease activity |
| Metadata ops ≥ 70% | metadata-heavy |
| Avg size < 32 KiB + high metadata | small-file metadata bound |
| Avg size > 256 KiB + read > 70% data | large-file sequential read |
| Read > 70% of data ops | read-heavy |
| Write > 70% of data ops | write-heavy |

---

## Phase 1 — Skeleton & CLI Wiring

**Deliverables:**
- [ ] `smb.py` module stub with `run(args)`, `discover_metrics()`, `VERSION`
- [ ] `vast-opstat.py` dispatch: `--smb` → `smb.run()`
- [ ] Remove "not implemented" exit for `--smb`
- [ ] Tests: CLI parse, dispatch, discover-metrics exits cleanly

**Approval checkpoint:** ☐ Phase 1 merged to feature branch

**Patterns to reuse:** `nfs_v41.py` module header, `init_config()`, `vast_api_log`, `tui_layout`

---

## Phase 2 — Core Monitors & Health Panel

**Deliverables:**
- [ ] Cluster monitor creation (multi-monitor if VMS forbids mixing)
- [ ] Telemetry engine selection:
  - Prefer instantaneous `SMBCommon` / `__rate` (NFS v4.1 pattern)
  - Fall back to counter delta if only `*_req` cumulative (NVMe pattern)
- [ ] Panels: Health & Workload + Performance Insights
- [ ] Refresh loop, `--sample-average`, `--refresh`

**Approval checkpoint:** ☐ Health panel validated on live SMB workload

---

## Phase 3 — Command Tables & Classification

**Deliverables:**
- [ ] DATA PATH panel (READ/WRITE)
- [ ] METADATA & NAMESPACE panel (CREATE, CLOSE, QUERY_*, SET_INFO)
- [ ] SESSION & LOCKING panel (or VMS PROXY sub-panel if gaps)
- [ ] Sort keys: `r` name, `o` ops, `l` latency, `w` workload %
- [ ] Hybrid fallback if `SMBCommon` reads zero (mirror NFS v4.1 supplement)

**Approval checkpoint:** ☐ Command table matches discovery inventory

---

## Phase 4 — Drill-Down

**Deliverables:**
- [ ] `c` cNode, `v` View/share, `t` Tenant (consistent with NFS — **not** VIP)
- [ ] Batch rank + batch display monitors (mandatory — NFS v3 lesson)
- [ ] Standby message during drill switch
- [ ] Scope-specific metrics (ViewMetrics / TenantMetrics — not SmbMetrics on view scope if VMS rejects)

**Approval checkpoint:** ☐ Drill-down ≤ 10 API calls on entry (rank + display)

---

## Phase 5 — Polish, Docs, Tests, Merge

**Deliverables:**
- [ ] `--csv` export
- [ ] `--log-api-calls` verified
- [ ] `tests/test_vast_opstat.py` — `TestSmbMetrics`, drill, dispatch
- [ ] `SMB_README.md` + screenshot `images/smb_tui.png`
- [ ] Update root `README.md`, `SETUP.md`, `images/README.md`
- [ ] Version bump to **0.1.2** across all protocol modules
- [ ] Merge `feat/vast-opstat-smb` → `main`

**Approval checkpoint:** ☐ Full pytest green, live smoke on var203, docs reviewed

---

## Keybind Map (final)

| Key | SMB action | Notes |
|-----|------------|-------|
| `c` | cNode drill-down | Backend skew |
| `v` | View / share drill-down | SMB export path — **not** VIP |
| `t` | Tenant drill-down | Multi-tenant isolation |
| `x` | Exit drill → cluster | Same as NFS |
| `Space` | Force refresh | |
| `r/o/l/w` | Sort modes | Same semantics as NFS v3 |
| `q` | Quit | |

---

## Expert Skills & References to Invoke Per Phase

| Phase | Skill / reference |
|-------|-------------------|
| 0 | Live VMS `--discover-metrics`; `vast-api-knowledge` monitor patterns |
| 0 | `scripts/macscope.py` — client-side SMB symptoms (oplock, signing, multichannel) for README correlation appendix |
| 1–5 | `vast-config-standard`, `vast-testing-standard` |
| 2–3 | `nfs_v41.py` instantaneous rate + proxy panel pattern |
| 3 | `nfs_v3.py` metadata vs data split, workload classifier |
| 4 | `nfs_v3.py` batch drill (`_is_batch_drill_mode`, `_rank_drill_candidates`) |
| 5 | `review-bugbot` / security review before merge |

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| SmbMetrics not exported per-command | Proxy panel + SMBCommon aggregates; document gaps in discover-metrics |
| View monitors reject aggregation | `no_aggregation=True` for view scope (NFS v3 fix) |
| Tenant scope needs delta engine | Reuse `_delta_rate_from_samples` from nfs_v3 |
| ProtoMetrics + SmbMetrics cannot mix | Separate monitors, client-side merge (NVMe pattern) |
| SMB disabled on lab cluster | Phase 0 gate blocked until SMB workload available |
| Keybind `v` confusion with NVMe VIP | SMB README explicitly states View/share |

---

## Out of Scope (v1)

- Per-client Windows SID drill-down (unless VMS exposes `smbclient` object_type with metrics)
- SMB multichannel per-channel breakdown (unless VIP/cnode metrics sufficient)
- macOS client correlation (macscope remains separate tool)
- Real-time packet capture (vast-sniff territory)
- SMB over QUIC / RDMA transport specifics

---

## Approval Sign-Off

| Phase | Approver | Date | Notes |
|-------|----------|------|-------|
| 0 — Discovery & layout | | | |
| 1 — Skeleton | | | |
| 2 — Health panel | | | |
| 3 — Command tables | | | |
| 4 — Drill-down | | | |
| 5 — Merge to main | | | |

**Do not write `smb.py` implementation code until Phase 0 is approved.**
