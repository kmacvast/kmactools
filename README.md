# kmactools

**Solutions Engineering Diagnostic, Automation, and Systems Interrogation Toolkit**

An optimized workspace for VAST Data Solutions Engineering: storage-fabric profiling, catalog-scale metadata analytics, communication intelligence harvesting, and lab virtualization diagnostics. Tools here are built for repeatable lab workflows, customer-facing demonstrations, and fast root-cause analysis—not ad hoc one-offs.

---

## Repository Statement of Intent

**kmactools** consolidates tactical utilities used across VAST SE engagements into a single, version-controlled repository. The collection spans three architectural pillars:

| Pillar | Path | Focus |
| :--- | :--- | :--- |
| **Storage fabric engineering** | [`vast/`](vast/) | Element Store catalog queries, capacity/DRR analysis, VMS auth, NFS monitoring, and audit tooling |
| **Communication intelligence** | [`timefinder/`](timefinder/) | Slack/Gmail message harvesting, thread heuristics, work-journal candidates, and Google Calendar sync |
| **Infrastructure diagnostics** | [`scripts/`](scripts/) | macOS scopes, virtualization debuggers, media transcription, and lab harness scripts |

Each module ships with its own README where operational detail matters. The root document stays intentionally high-level.

---

## High-Level Architectural Core Modules

### `vast/` — VAST Data Platform SE Toolkit

The primary engineering surface. Sub-modules cover authentication (`auth/`), shared config helpers (`common/`), identity/AD inspection (`identity/`), the flagship unified catalog CLI (`vast-catalog/vcatalog_tool.py`), VASTDB time-series ingest (`vast-db/`), logical-vs-physical capacity reporters (`vast-du/`), the live multi-protocol performance monitor (`vast-opstat/`), protocol sniffing (`vast-sniff/`), and storage-plane viewers (`vast-viewer/`).

**Flagship entry point:** [`vast/vast-catalog/vcatalog_tool.py`](vast/vast-catalog/vcatalog_tool.py) — parallel streaming catalog analytics, early-exit search, VMS-backed DRR dashboards, and multi-protocol path/S3 operations. See [`vast/vast-catalog/README.md`](vast/vast-catalog/README.md) and [`vast/vast-catalog/USAGE.md`](vast/vast-catalog/USAGE.md).

### `timefinder/` — Communication Intelligence & Harvesting

A local, rule-based pipeline that extracts Slack and Gmail activity, clusters conversations, scores work-journal candidates, supports interactive ICS review, and syncs approved entries to Google Calendar—without LLM inference during candidate scoring.

### `scripts/` — Infrastructure Diagnostics & Workspace Automation

Quick-strike operational utilities: macOS kernel scopes, YouTube transcription wrappers, VMware analyzers, SELab data-services harnesses, and other lab automation helpers that do not belong in the VAST-specific tree.

---

## Primary Entry-Point Guidance

### Prerequisites

- **Python 3.10+** (3.14+ supported; some modules require 3.8+ stdlib-only)
- **Virtual environment** (strongly recommended)
- **VAST lab credentials** where applicable (`~/.vastconf` or `~/.vast-catalog-config.json` depending on tool)
- **NFS mount reachability** for catalog seeding and S3-tag modes (`/mnt/kmac` or lab-specific path)

### Clone & environment setup

```bash
git clone git@github.com:kmacvast/kmactools.git
cd kmactools

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Install dependencies for the module you intend to run, e.g.:
pip install -r vast/vast-catalog/requirements.txt
pip install vastpy pytest pytest-mock   # common lab additions
```

### Recommended first commands

```bash
# VAST catalog platform guide (no credentials required for --about text)
./vast/vast-catalog/vcatalog_tool.py --about

# Run root regression suite (mocked; no live VMS)
python3 -m unittest discover -s tests -p 'test_*.py'

# Generate a VMS API token (requires ~/.vastconf)
python3 vast/auth/vast_get_token.py
```

Configure credentials before any live cluster operation. Module-specific setup lives in each subdirectory's README.

---

## Repository Contents & Tool Index

**For an exhaustive, itemized map of every tool, diagnostic utility, and test script inside this repository—along with descriptions of exactly what they do—please refer to the [Repository Content Guide (REPO_CONTENT.md)](REPO_CONTENT.md).**

---

## Testing

Central regression tests live under [`tests/`](tests/). Run from the repository root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
# or, where pytest is installed:
pytest tests/
```

Live integration harnesses (e.g. [`vast/vast-catalog/run_vcat_test_suite.sh`](vast/vast-catalog/run_vcat_test_suite.sh)) require lab credentials and a reachable NFS mount.

---

## License

This project is licensed under the terms of the [LICENSE](LICENSE) file in the repository root.

---

**Maintainer:** KMac kmac@vastdata.com · **Primary VAST docs:** [`vast/README.md`](vast/README.md) · **Catalog manual:** [`vast/vast-catalog/USAGE.md`](vast/vast-catalog/USAGE.md)
