# kmactools Documentation

The documentation hub for **kmactools** — the VAST Solutions Engineering diagnostic,
automation, and systems-interrogation toolkit. Start here, then branch to the guide or
module you need.

---

## Start here

| I want to… | Go to |
|---|---|
| Understand what this repo is and how it's organized | [Architecture](architecture.md) |
| Install Python, clone, and run my first command | [Getting Started](getting-started.md) |
| Configure credentials for a VAST cluster | [Credentials](credentials.md) |
| Run the test suites | [Testing](testing.md) |
| Find a specific script or tool | [Tool Index](tool-index.md) |

---

## Module documentation

Each module keeps its own docs next to the code. This hub links out to them.

### `vast/` — VAST Data Platform toolkit

| Module | What it does | Docs |
|---|---|---|
| **vast-catalog** | Element Store catalog analytics, search, DRR, S3 tagging | [README](../vast/vast-catalog/README.md) · [USAGE](../vast/vast-catalog/USAGE.md) · [ALGORITHM](../vast/vast-catalog/ALGORITHM.md) |
| **vast-opstat** | Live multi-protocol performance monitor (NFS v3/v4.1, NVMe-oTCP, SMB) | [README](../vast/vast-opstat/README.md) · [SETUP](../vast/vast-opstat/SETUP.md) |
| **vast-du** | Directory logical vs physical capacity + DRR reporter | [README](../vast/vast-du/README.md) |
| **vast-db** | VASTDB market time-series ingest & telemetry dashboards | [README](../vast/vast-db/README.md) |
| **vast-viewer** | Read-only VAST config inspector (clean JSON output) | [README](../vast/vast-viewer/README.md) |
| **vast-sniff** | Leader-node packet capture helper | [README](../vast/vast-sniff/README.md) |
| **auth** | VMS API token lifecycle | [README](../vast/auth/README.md) |
| **common** | Shared `load_vast_config()` helper | [README](../vast/common/README.md) |
| **identity** | Active Directory / identity inspection | [README](../vast/identity/README.md) |

### `timefinder/` — Communication intelligence

| Doc | Purpose |
|---|---|
| [README](../timefinder/README.md) | Day-to-day workflow and CLI |
| [ARCHITECTURE](../timefinder/ARCHITECTURE.md) | Modules, data flow, auth |
| [HEURISTICS](../timefinder/HEURISTICS.md) | Scoring, clustering, dedup rules |
| [SETUP_macOS](../timefinder/SETUP_macOS.md) | First-time macOS setup |

### `scripts/` — Infrastructure diagnostics

Quick-strike lab utilities (macOS scopes, VMware analysis, transcription, harnesses).
See the [Tool Index](tool-index.md#scripts) for the itemized list.

---

## Developer / working docs

Design records and research artifacts that are not part of the user-facing surface live
under [`docs/dev/`](dev/):

- [SMB implementation plan](dev/smb/SMB_IMPLEMENTATION_PLAN.md)
- [SMB Phase 0 discovery results](dev/smb/SMB_PHASE0_RESULTS.md)

---

**Maintainer:** KMac · kmac@vastdata.com
