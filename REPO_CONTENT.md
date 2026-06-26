# Repository Content Guide

**kmactools** — itemized directory index and tool reference.

This document complements the executive [README.md](README.md). Use it when you need to locate a specific script, understand what a subdirectory owns, or decide which module README to open next.

---

## Top-Level Layout

```text
kmactools/
├── timefinder/        Communication intelligence & message harvesting
├── scripts/           Infrastructure diagnostics & lab automation
├── tests/             Root regression / mock verification suite
├── vast/              VAST Data Platform SE engineering toolkit
├── LICENSE
├── README.md          Executive landing page
└── REPO_CONTENT.md    ← You are here
```

---

## 1. `timefinder/` — Communication Intelligence & Harvesting Framework

**What it is:** A diagnostic message extraction and activity processing suite for building evidence-backed work journals from local Slack and Gmail backups.

**What it does:** Authenticates with Slack workspace endpoints (via CLI tokens) and Google Calendar (OAuth2), executes high-volume text harvesting into `~/.timefinder_cache/`, resolves channel/DM mappings, clusters conversation threads, applies weighted heuristics to surface calendar-worthy work blocks, supports interactive ICS review, and syncs approved entries to Google Calendar—all locally for scoring, without LLM inference.

| Item | Role |
| :--- | :--- |
| `timefinder.py` | Unified CLI for all TimeFinder capabilities |
| `channels_init.py` | Bootstrap hardcoded channel list → Slack IDs |
| `channels_resolve.py` | Interactive resolver for channels, DMs, group DMs |
| `message_gather.py` | Gather Slack and/or Gmail messages to local cache |
| `candidates.py` | Score and emit reviewable calendar candidate files |
| `ics_review.py` | Interactive ICS review wizard |
| `google_calendar.py` | Google OAuth and Calendar sync |
| `slack_messages.py` | Slack API / backup helpers |
| `gmail_messages.py` | Gmail IMAP helpers |
| `thread_harvest.py` | Full channel + thread JSON harvest |
| `HEURISTICS.md` | Scoring, clustering, dedup, and noise-filter documentation |
| `SETUP_macOS.md` | First-time macOS + Slack CLI setup |
| `README.md` | Module workflow, config, and usage |
| `tests/` | TimeFinder unit tests |

**Platform note:** macOS-focused setup; see `SETUP_macOS.md`.

---

## 2. `scripts/` — Infrastructure Diagnostics & Workspace Automation

**What it is:** A collection of systemic target monitors, lab harnesses, and transcription helpers outside the VAST-specific tree.

**What it does:** Houses quick-strike operational utilities for day-to-day SE and lab work—macOS introspection, virtualization debugging, media processing, and scripted test environments.

| Script | Purpose |
| :--- | :--- |
| `macscope.py` | macOS kernel / system scope diagnostics |
| `vmw-analyzer.py` | VMware virtualization log and state analysis |
| `yt-transcribe.sh` | YouTube audio fetch + transcription wrapper |
| `selab_ds_harness.py` | SELab data-services test harness (Python) |
| `selab-ds-test.sh` | SELab data-services shell test driver |
| `find_locked_debug.py` | Locked-file / debug trace helper |
| `inject-time.sh` | Time-injection utility for lab scenarios |
| `fibonacci.sh` | Lightweight shell benchmark / demo |
| `tc_enhanced.sh` | Enhanced traffic-control / network shaping helper |

---

## 3. `vast/` — VAST Data Platform SE Engineering Toolkit Root

**What it is:** The core specialized module tree for VAST Element Store profiling, VMS REST integration, VASTDB analytics, and storage-plane auditing.

**What it does:** Provides end-to-end tooling from credential lifecycle through catalog-scale metadata search, capacity estimation, NFS performance monitoring, and configuration validation—optimized for Solutions Engineering lab and customer briefing workflows.

Overview table: [`vast/README.md`](vast/README.md)

### `vast/auth/`

VAST API token extraction and authentication lifecycle handlers.

| File | Purpose |
| :--- | :--- |
| `vast_get_token.py` | Exchange `~/.vastconf` user/password for a long-lived REST API token (`POST /api/apitokens/`) |
| `README.md` | Credential format and usage |

### `vast/common/` & `vast/identity/`

Cross-module utilities and identity configuration parsers.

| Path | Purpose |
| :--- | :--- |
| `common/utils.py` | Shared `load_vast_config()` helper; tenant normalization for Global Admin auth |
| `identity/show_ad_configs.py` | Inspect Active Directory / LDAP configurations via VMS REST (`VMS_TOKEN`) |

### `vast/vast-catalog/` ⭐ Flagship Module

Production parallel streaming catalog indexer, early-exit search engine, multi-protocol S3 tagger, and live integration harness.

| File | Purpose |
| :--- | :--- |
| **`vcatalog_tool.py`** | Unified CLI (v1.3.7): capacity histograms, cold-file audit, owner/security analysis, quota registration, metadata search, DRR dashboards, path translation, S3 tags, lab seeding |
| `run_vcat_test_suite.sh` | **11-stage** live integration verification harness (catalog + VMS + S3 + search) |
| `README.md` | Architectural overview and VAST metaspace glossary |
| `USAGE.md` | Exhaustive CLI flag matrix, config schema, output mockups |
| `ALGORITHM.md` | Streaming fold/merge internals |
| `vast-catalog-config.example.json` | Single-file credential template (`~/.vast-catalog-config.json`) |
| `requirements.txt` | Python deps: `vastdb`, `pyarrow`, `pandas`, `boto3`, … |
| `find_files_nfs.py` | Legacy NFS find helper (superseded by catalog search) |
| `vcatalog_cyberdemo.py` | Cyber-demo variant script |
| `test_vcatalog_tool.py` | Legacy local unittest stub; prefer repo-root `tests/test_vcatalog_tool.py` |

### `vast/vast-db/`

Real-time financial market time-series ingest engines and tabular analytics against VASTDB.

| File | Purpose |
| :--- | :--- |
| `alltick_to_vastdb.py` | AllTick market data → VASTDB ingest |
| `read_ticks.py` | Read/query tick records from VASTDB |
| `mon_vastdb_records.py` | Monitor VASTDB record counts / health |
| `chart_creator.py` | Chart generation from stored tick data |

### `vast/vast-du/`

Advanced multi-threaded logical vs unique capacity estimators and dataset entropy simulators.

| File | Purpose |
| :--- | :--- |
| `vast-du.py` | Directory efficiency reporter: logical, unique, physical, DRR tiers via VMS |
| `vast-entropy-sim.py` | Entropy / compressibility simulation for lab datasets |
| `README.md` | Metrics glossary and setup |

### `vast/vast-nfstop/`

Terminal interactive, top-like real-time transaction monitor for cluster NFS mount paths.

| File | Purpose |
| :--- | :--- |
| `vast-nfstop.py` | Live NFS RPC op rates, latency, throughput, workload classification (stdlib-only) |
| `README.md` | Display layout, VMS query parameters, credits |

### `vast/vast-sniff/`

Low-level protocol frame tracing and analysis scripts.

| File | Purpose |
| :--- | :--- |
| `vast-sniff.sh` | Shell-based stream / protocol sniffing utilities |

### `vast/vast-viewer/`

Storage-plane configuration validators and active object auditors.

| File | Purpose |
| :--- | :--- |
| `vast-viewer.py` | VAST viewer CLI for storage-plane inspection |
| `audit_vast_viewer.py` | Audit helper for viewer configurations |
| `test_vast_viewer.py` | Viewer module tests |
| `README.md` | Usage and configuration |

---

## 4. `tests/` — Root Operational Verification Layer

**What it is:** Central regression testing layout tracking module logic boundaries across the repository.

**What it does:** Runs automated unit and mock cycles ensuring local enhancements do not introduce regressions before live lab validation. Tests are designed to **mock VASTClient / VASTDB** and avoid hitting production VMS endpoints unless explicitly labeled integration tests.

| Test file | Covers |
| :--- | :--- |
| `test_vcatalog_tool.py` | **`vcatalog_tool.py`** — 48+ mocked tests: streaming search, DRR math, parallel aggregation, credentials, argparse |
| `test_vast_du.py` | **`vast-du.py`** — capacity metric and config logic |
| `test_utils.py` | **`vast/common/utils.py`** — `load_vast_config()` tenant normalization |
| `test_vcatalog_cyberdemo.py` | **`vcatalog_cyberdemo.py`** — cyber-demo script behavior |

### How to run

From repository root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Module-specific live harness (requires lab):

```bash
cd vast/vast-catalog && ./run_vcat_test_suite.sh
```

---

## Quick Navigation by Task

| I need to… | Go to |
| :--- | :--- |
| Search 44M+ catalog files without crawling NFS | `vast/vast-catalog/vcatalog_tool.py --search` · [USAGE.md](vast/vast-catalog/USAGE.md) |
| Show DRR dedup/similarity/compression pillars | `vcatalog_tool.py --show-data-reduction-rates` |
| Get a VMS API token | `vast/auth/vast_get_token.py` |
| Monitor live NFS ops on cluster | `vast/vast-nfstop/vast-nfstop.py` |
| Report directory logical vs physical usage | `vast/vast-du/vast-du.py` |
| Harvest Slack/Gmail for work journal | `timefinder/timefinder.py --gather-candidate-entries` · [timefinder/README.md](timefinder/README.md) |
| Run all mock regressions | `python3 -m unittest discover -s tests` |

---

## Related Documentation Index

| Document | Location |
| :--- | :--- |
| Executive README | [README.md](README.md) |
| VAST module overview | [vast/README.md](vast/README.md) |
| Catalog architecture | [vast/vast-catalog/README.md](vast/vast-catalog/README.md) |
| Catalog CLI manual | [vast/vast-catalog/USAGE.md](vast/vast-catalog/USAGE.md) |
| TimeFinder workflow | [timefinder/README.md](timefinder/README.md) |
| VAST-DU metrics | [vast/vast-du/README.md](vast/vast-du/README.md) |
| NFS monitor | [vast/vast-nfstop/README.md](vast/vast-nfstop/README.md) |
