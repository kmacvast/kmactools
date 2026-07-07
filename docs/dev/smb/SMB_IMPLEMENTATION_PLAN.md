# vast-opstat — SMB Protocol Implementation Plan

**Branch:** `feat/vast-opstat-smb`  
**Status:** Phase 5 complete — v0.1.2; merge to `main` pending approval  
**Tool version target:** 0.1.2 (SMB release)  
**Author:** KMac kmac@vastdata.com

---

## Approved Design Decisions (2026-07-06)

| Decision | Status |
|----------|--------|
| 5-panel layout order (Health → Insights → Data → Metadata → Session) | ✅ Approved |
| Phase 0 live metric discovery | ✅ Approved |
| Drill keys `c` / `v` / `t` / `x` | ✅ Approved |
| Client IP scoping (`--client` / `--clients`) | ✅ Design now; implement Phase 4b |


## Executive Summary

SMB workloads differ fundamentally from NFS and block:

| Dimension | NFS v3 | NFS v4.1 | NVMe-oTCP | **SMB (target)** |
|-----------|--------|----------|-----------|------------------|
| Primary unit | Stateless RPC | Session + compounds | LBA I/O | **Session + tree + file handle** |
| Pain signal | READDIR / LOOKUP storms | Stateful proxies | Fabric/reclaim | **QUERY_DIR, CREATE/CLOSE, lease breaks** |
| Client model | Mount + inode | Client ID | Host NQN | **Windows/macOS session + share** |
| Metadata weight | High (RPC table) | Proxy panel | Low | **Dominant in real deployments** |
| Drill `v` key | View path | View path | **VIP** | **View / share path** |

The SMB module must answer the SE question: *"Is the customer slow on data, metadata, connection setup, or locking — and where (cluster, share, tenant, cNode, **or specific client IP**)?"* within one terminal screen.

---

## Client IP Scoping — Design (Phase 4b)

**User story:** SE enters one or more client IPs and sees only SMB activity attributable to those hosts — the most common field-debug workflow after cluster-wide view.

### CLI flags (mirror NVMe `--volumes` pattern)

| Flag | Example | Behavior |
|------|---------|----------|
| `--client IP` | `--client 10.20.30.40` | Alias for `--clients` (single host) |
| `--clients a,b,c` | `--clients 10.1.1.5,10.1.1.6` | Comma-separated client IPs or hostnames |

When active, title bar shows: `Clients: 10.20.30.40 (+2)` instead of `All Clients`.

### Resolution flow (determined in Phase 0 discovery)

```
--clients IP list
    ├── GET client endpoint (candidate: /smbclients/, /clients/, …)
    ├── Match by ip / address / hostname field
    ├── object_type=? + object_ids=[…]  → scoped monitors
    └── If no object API: document fallback (cluster view + client column filter if VMS supports)
```

### UI impact when client-scoped

| Panel | Scoped behavior |
|-------|-----------------|
| Health | Totals for selected clients only |
| Insights | Top command among client traffic |
| Command tables | Same rows, client-filtered rates |
| Drill `c`/`v`/`t` | Still available; shows skew **for that client's traffic path** |

### Optional future key: `h` (client host list)

Not in v1 keybind approval. If Phase 0 finds a ranked client list API, add **`h`** drill-down (like NVMe host initiators) in Phase 4b — ranked by ops/s across all connected SMB clients, filterable to `--clients` subset.

### Phase placement

| Phase | Client work |
|-------|-------------|
| 0 | Discover client object endpoint + IP field names |
| 1 | Add argparse stubs for `--client`/`--clients` (no-op until 4b) |
| 4b | Implement client resolution + scoped monitors |
| 5 | Document in `SMB_README.md` with examples |

---

## Phase 0 — Metric Discovery & Design Gate (READ-ONLY)

**Goal:** Confirm what VMS actually exports before locking UI layout.  
**Operation class:** Read-only (`GET /api/metrics/`, `POST /api/monitors/`, `--discover-metrics`).  
**Approval checkpoint:** ✅ Layout + discovery approved 2026-07-06

**Discovery tooling:**

```bash
cd vast/vast-opstat
python3 smb_phase0_discover.py --vms <HOST> --user admin
# writes SMB_PHASE0_RESULTS.md
```

Results: [SMB_PHASE0_RESULTS.md](SMB_PHASE0_RESULTS.md)  
**Live run:** ✅ var203 2026-07-06 — see results for metric binding decisions.

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

- [x] `discover-metrics` output captured (var203)
- [x] Table: **all `SmbMetrics` per-command unexported** (HTTP 400 `property_error`)
- [x] `object_type` matrix: cluster/view/tenant/cnode OK; **all client endpoints 404**
- [x] Monitor mixing: SMBCommon-only monitors work; do not include SmbMetrics props
- [x] View monitor: `view_no_aggregation` OK

### 0.3 Proxy panel decision (var203 validated)

Per-command `SmbMetrics` is **not exported** on var203. Use **SMBCommon aggregate rows** (not fabricated command rates):

| Panel row | SMBCommon source (confirmed) |
|-----------|-------------------------------|
| READ | `rd_iops`, `rd_bw`, `read_latency__avg`, `read_size__avg` |
| WRITE | `wr_iops`, `wr_bw`, `write_latency__avg`, `write_size__avg` |
| METADATA | `md_iops`, `rd_md_iops`, `wr_md_iops` |
| SESSION/LOCK | `NfsMetrics,nfs3_smb_interop_*` when > 0; else dimmed placeholder |
| Health headline | `iops`, `bw`, aggregate latency |

**Gate rule:** ✅ Phase 0 complete — Phase 2 proceeds with SMBCommon-only binding per [SMB_PHASE0_RESULTS.md](SMB_PHASE0_RESULTS.md).

---

## Phase 4b — Client IP Scoping (post core drill-down)

**Deliverables:**
- [ ] Resolve `--client` / `--clients` to VMS object IDs (from Phase 0 endpoint)
- [ ] Scoped monitors for selected client IPs
- [ ] Title bar + health panel reflect client filter
- [ ] Optional `h` key: ranked connected SMB clients (if API supports)
- [ ] Tests: client resolution, invalid IP handling, multi-client merge

**Approval checkpoint:** ☐ Client scoping validated with 2+ simultaneous clients

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

┌─ SMB2 OPCODE WORKFLOW ──────────────────────────────────────────────────┐
│  SMB2 Opcode        Ops/s    Throughput   Avg Size   Latency   Source   │
│  Data path                                                                │
│  SMB2_READ          2,840    1.62 GB/s    592 KB     620 µs    MEASURED  │
│  SMB2_WRITE         1,020    0.48 GB/s    472 KB     1.1 ms    MEASURED  │
│  Metadata                                                                 │
│  METADATA (total)   7,200    —            —          —         AGGREGATE  │
│      read-md 4,100/s  ·  write-md 3,100/s                                 │
│  (empty opcodes omitted — only live data shown each refresh)              │
└─────────────────────────────────────────────────────────────────────────┘

 Footer: c=cNode  v=View/Share  t=Tenant  x=exit drill  Space=refresh  q=quit
```

### Why this block order

1. **Health first** — immediate answer: idle, healthy, degraded, metadata-dominated.
2. **Insights second** — narrows investigation before opcode detail.
3. **Opcode workflow third** — unified data + metadata + session evidence; only active opcodes.

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
- [x] `smb.py` module stub with `run(args)`, `discover_metrics()`, `VERSION`
- [x] `vast-opstat.py` dispatch: `--smb` → `smb.run()`
- [x] Remove "not implemented" exit for `--smb`
- [x] Tests: CLI parse, dispatch, discover-metrics exits cleanly

**Approval checkpoint:** ☑ Phase 1 merged to feature branch

**Patterns to reuse:** `nfs_v41.py` module header, `init_config()`, `vast_api_log`, `tui_layout`

---

## Phase 2 — Core Monitors & Health Panel

**Deliverables:**
- [x] Cluster monitor creation (multi-monitor if VMS forbids mixing)
- [x] Telemetry engine selection:
  - Prefer instantaneous `SMBCommon` / `__rate` (NFS v4.1 pattern)
  - Fall back to counter delta if only `*_req` cumulative (NVMe pattern)
- [x] Panels: Health & Workload + Performance Insights
- [x] Refresh loop, `--sample-average`, `--refresh`

**Approval checkpoint:** ☑ Health panel validated on live SMB workload

---

## Phase 3 — Aggregate Panels & Classification (revised post-Phase 0)

**Note:** Per-command `SmbMetrics` table **cancelled** on var203 — opcode panel uses SMBCommon aggregates with explicit source labeling.

**Deliverables:**
- [x] SMB2 OPCODE WORKFLOW panel (replaces separate DATA / METADATA / SESSION panels)
- [x] Only opcodes with live data shown each refresh (no empty dash rows)
- [x] `METADATA (total)` aggregate row + compact read-md / write-md sub-line
- [x] READ/WRITE measured from `rd_*` / `wr_*`; session/lock proxies from REST when available
- [x] Classifier uses `md_iops/iops` ratio (no per-command top contributor until VMS exports SmbMetrics)

**Approval checkpoint:** ☑ Opcode panel validated on live SMB workload (var203)

---

## Phase 4 — Drill-Down

**Deliverables:**
- [x] `c` cNode, `v` View/share, `t` Tenant (consistent with NFS — **not** VIP)
- [x] Batch rank + batch display monitors (mandatory — NFS v3 lesson)
- [x] Standby message during drill switch
- [x] Scope-specific metrics (ViewMetrics / TenantMetrics — not SmbMetrics on view scope if VMS rejects)

**Approval checkpoint:** ☑ Drill-down ≤ 10 API calls on entry (rank + display)

---

## Phase 5 — Polish, Docs, Tests, Merge

**Deliverables:**
- [x] `--csv` export
- [x] `--log-api-calls` verified
- [x] `tests/test_vast_opstat.py` — `TestSmbModule`, drill, dispatch
- [x] `SMB_README.md` + screenshot `images/smb_tui.png`
- [x] Update root `README.md`, `SETUP.md`, `images/README.md`
- [x] Version bump to **0.1.2** across all protocol modules
- [x] Merge `feat/vast-opstat-smb` → `main` (PR #9)

**Approval checkpoint:** ☑ pytest green; live smoke validated; merged via PR #9

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
| SmbMetrics not exported per-command | ✅ Confirmed var203 — SMBCommon aggregate panels only; label as VMS PROXY |
| View monitors reject aggregation | `no_aggregation=True` for view scope (NFS v3 fix) |
| Tenant scope needs delta engine | Reuse `_delta_rate_from_samples` from nfs_v3 |
| ProtoMetrics + SmbMetrics cannot mix | Separate monitors, client-side merge (NVMe pattern) |
| SMB disabled on lab cluster | Phase 0 gate blocked until SMB workload available |
| Keybind `v` confusion with NVMe VIP | SMB README explicitly states View/share |

---

## Out of Scope (v1.0)

- macOS client correlation (macscope remains separate tool)
- Real-time packet capture (vast-sniff territory)
- SMB over QUIC / RDMA transport specifics
- SMB multichannel per-channel breakdown (unless VIP drill suffices)

**Planned for v1.x (Phase 4b):** ~~`--client` / `--clients` IP scoping~~ **Done in v0.1.2**

---

## Approval Sign-Off

| Phase | Approver | Date | Notes |
|-------|----------|------|-------|
| 0 — Discovery & layout | KMac | 2026-07-06 | 3 panels + opcode workflow, c/v/t/x, `--clients` |
| 1 — Skeleton | KMac | 2026-07-06 | `smb.py`, CLI dispatch, Phase 0 wrapper |
| 2 — Health panel | KMac | 2026-07-06 | SMBCommon cluster monitor |
| 3 — Command tables | KMac | 2026-07-06 | Aggregate proxy panels (no SmbMetrics) |
| 4 — Drill-down | KMac | 2026-07-06 | c/v/t batch rank+display |
| 4b — Client IP scoping | KMac | 2026-07-06 | `--clients` topn + session APIs |
| 5 — Merge to main | | | Pending pytest + approval |

**Phase 1–5 code complete on `feat/vast-opstat-smb` (v0.1.2).**
