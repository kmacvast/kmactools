# Tool Index

Itemized inventory of every tool, script, and doc in the repository. Use this when you
need to locate a specific script or decide which module to open next. For orientation,
start at [Architecture](architecture.md); to run something, see [Getting Started](getting-started.md).

---

## Top-level layout

```text
kmactools/
├── docs/              Documentation hub (you are here)
├── timefinder/        Communication intelligence & message harvesting
├── scripts/           Infrastructure diagnostics & lab automation
├── tests/             Root regression / mock verification suite
├── vast/              VAST Data Platform SE engineering toolkit
├── dev-requirements.txt
├── LICENSE
└── README.md          Executive landing page
```

---

## `vast/` — VAST Data Platform toolkit

### `vast/auth/`

| File | Purpose |
|---|---|
| `vast_get_token.py` | Exchange `~/.vastconf` user/password for a long-lived REST API token (`POST /api/apitokens/`) |
| `README.md` | Credential format and usage |

### `vast/common/`

| File | Purpose |
|---|---|
| `utils.py` | Shared `load_vast_config()`; tenant normalization for Global-Admin auth |
| `README.md` | Loader contract and usage |

### `vast/identity/`

| File | Purpose |
|---|---|
| `show_ad_configs.py` | List Active Directory configs via VMS REST (`VMS_TOKEN` env) |
| `README.md` | Usage and environment |

### `vast/vast-catalog/` ⭐ Flagship

| File | Purpose |
|---|---|
| **`vcatalog_tool.py`** | Unified CLI (v1.3.7): capacity histograms, cold-file audit, owner/security analysis, quota registration, metadata search, DRR dashboards, path translation, S3 tags, lab seeding |
| `run_vcat_test_suite.sh` | Multi-stage live integration harness (catalog + VMS + S3 + search) |
| `find_files_nfs.py` | NFS find helper (superseded by catalog search) |
| `vcatalog_cyberdemo.py` | Cyber-demo variant script |
| `vast-catalog-config.example.json` | Credential template (`~/.vast-catalog-config.json`) |
| `requirements.txt` | `vastdb`, `pyarrow`, `pandas`, `boto3`, … |
| `README.md` / `USAGE.md` / `ALGORITHM.md` | Architecture / CLI manual / streaming internals |

### `vast/vast-db/`

Real-time market time-series ingest and tabular analytics against VASTDB. Config:
`~/.vast-ingestor`.

| File | Purpose |
|---|---|
| `alltick_to_vastdb.py` | AllTick websocket market data → VASTDB micro-batched ingest |
| `read_ticks.py` | Read/query tick records from VASTDB |
| `mon_vastdb_records.py` | Live record-count / capacity monitor (ACID snapshot polling) |
| `chart_creator.py` | Streamlit + Plotly telemetry dashboard |
| `README.md` | Setup and script guide |

### `vast/vast-du/`

| File | Purpose |
|---|---|
| `vast-du.py` | Directory efficiency reporter: logical, unique, physical, DRR tiers via VMS |
| `vast-entropy-sim.py` | Entropy / compressibility simulation for lab datasets |
| `README.md` | Metrics glossary and setup |

### `vast/vast-opstat/`

Terminal, top-like real-time **multi-protocol** performance monitor. Stdlib-only at
runtime.

| File | Purpose |
|---|---|
| `vast-opstat.py` | Unified CLI + protocol dispatch; launches the interactive wizard when run with no args on a TTY |
| `wizard.py` | Interactive setup wizard (`--menu` / `-i`); emits argv, exports secrets via env |
| `nfs_v3.py` | NFS v3 engine |
| `nfs_v41.py` | NFS v4.1 engine (hybrid `NFS4Common`/`NfsMetrics`) |
| `nvme_tcp.py` | NVMe-oTCP block engine (counter-delta rates, volume scoping) |
| `smb.py` | SMB engine (opcode workflow, session/lock panels, client scoping) |
| `vast_common.py` | Shared REST transport, monitor lifecycle, signals, terminal I/O, cluster OS-version fetch |
| `tui_layout.py` | Shared table/color/box/formatter/glyph helpers |
| `vast_api_log.py` | Optional VMS REST logging (`--log-api-calls`) |
| `openmetrics.py` | Optional OpenMetrics/OTel JSON Lines metrics export (`--export-openmetrics`) |
| `smb_phase0_discover.py` | SMB metric discovery probe |
| `images/` | TUI screenshots |
| `README.md` / `SETUP.md` | Usage matrix / beginner install guide |
| `NFSv3_README.md`, `NFSv41_README.md`, `NVMe_TCP_README.md`, `SMB_README.md`, `SMB_OPCODES.md` | Per-protocol references |

> SMB design/research artifacts (`SMB_IMPLEMENTATION_PLAN.md`, `SMB_PHASE0_RESULTS.md`)
> live under [`docs/dev/smb/`](dev/smb/).

### `vast/vast-sniff/`

| File | Purpose |
|---|---|
| `vast-sniff.sh` | Leader-node `tcpdump` capture helper (run inside the platform container) |
| `README.md` | Usage and safety notes |

### `vast/vast-viewer/`

| File | Purpose |
|---|---|
| `vast-viewer.py` | Read-only VAST config inspector (clean JSON/CSV/table output) |
| `audit_vast_viewer.py` | Post-change validation wrapper |
| `README.md` | Usage and configuration |

---

## `timefinder/`

Local, rule-based Slack/Gmail harvesting → work-journal candidates → Google Calendar.

| Item | Role |
|---|---|
| `timefinder.py` | Unified CLI for all capabilities |
| `channels_init.py` / `channels_resolve.py` | Channel bootstrap / interactive resolver |
| `message_gather.py` | Gather Slack and/or Gmail messages to local cache |
| `candidates.py` | Score and emit reviewable calendar candidates |
| `ics_review.py` | Interactive ICS review wizard |
| `google_calendar.py` | Google OAuth and Calendar sync |
| `slack_messages.py` / `gmail_messages.py` / `thread_harvest.py` | API / backup / harvest helpers |
| `README.md` / `ARCHITECTURE.md` / `HEURISTICS.md` / `SETUP_macOS.md` | Workflow / design / scoring / setup |
| `tests/` | TimeFinder unit tests |

---

## `scripts/`

| Script | Purpose |
|---|---|
| `macscope.py` | macOS kernel / system scope diagnostics |
| `vmw-analyzer.py` | VMware virtualization log/state analysis |
| `yt-transcribe.sh` | YouTube audio fetch + transcription wrapper |
| `selab_ds_harness.py` / `selab-ds-test.sh` | SELab data-services test harness / driver |
| `Invoke-SmbOpstatLoad.ps1` | Windows SMB load generator for vast-opstat testing |
| `find_locked_debug.py` | Locked-file / debug trace helper |
| `inject-time.sh` | Time-injection utility for lab scenarios |
| `fibonacci.sh` | Lightweight shell benchmark / demo |
| `tc_enhanced.sh` | Traffic-control / network shaping helper |

---

## `tests/`

Central mocked regression suite. See [Testing](testing.md) for the full coverage table and
how to run it.

---

## Quick navigation by task

| I need to… | Go to |
|---|---|
| Search millions of catalog files without crawling NFS | `vast/vast-catalog/vcatalog_tool.py --search` · [USAGE](../vast/vast-catalog/USAGE.md) |
| Show DRR dedup/similarity/compression pillars | `vcatalog_tool.py --show-data-reduction-rates` |
| Get a VMS API token | `vast/auth/vast_get_token.py` |
| Monitor live protocol perf (NFS/NVMe/SMB) | `vast/vast-opstat/vast-opstat.py` · [README](../vast/vast-opstat/README.md) |
| Report directory logical vs physical usage | `vast/vast-du/vast-du.py` |
| Harvest Slack/Gmail for a work journal | `timefinder/timefinder.py` · [README](../timefinder/README.md) |
| Run all mock regressions | `pytest tests/` |
