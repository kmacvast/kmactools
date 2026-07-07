# Getting Started

This guide gets you from a fresh clone to your first working command. For tool-specific
setup (e.g. a no-Python-experience walkthrough for `vast-opstat`), follow the module doc
linked at the end.

---

## Prerequisites

- **Python 3.10+** recommended (some modules run on 3.8+; `vast-opstat` is stdlib-only).
- **A virtual environment** (strongly recommended).
- **VAST lab credentials** where a tool talks to a cluster — see [Credentials](credentials.md).
- **NFS mount reachability** for catalog seeding / S3-tag modes (e.g. `/mnt/kmac`).

---

## Clone and create a virtual environment

```bash
git clone git@github.com:kmacvast/kmactools.git
cd kmactools

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
```

---

## Install dependencies

Dependencies are **per-module**. Install only what the tool you're running needs.

```bash
# vast-catalog (VASTDB analytics)
pip install -r vast/vast-catalog/requirements.txt

# Common VMS tools (vast-viewer, vast-du, auth, identity)
pip install vastpy

# Everything needed to run the full test matrix
pip install -r dev-requirements.txt
```

> `vast-opstat` needs **no** third-party packages to run — only the standard library.

---

## First commands

```bash
# VAST catalog platform education (no credentials needed for --about)
./vast/vast-catalog/vcatalog_tool.py --about

# Live performance monitor — interactive wizard (no flags needed)
./vast/vast-opstat/vast-opstat.py

# Generate a VMS API token (requires ~/.vastconf)
python3 vast/auth/vast_get_token.py

# Run the mocked regression suite
pytest tests/
```

Configure credentials before any live cluster operation — see [Credentials](credentials.md).

---

## Where to go next

| Tool | Deep-dive |
|---|---|
| Multi-protocol performance monitor | [vast-opstat SETUP](../vast/vast-opstat/SETUP.md) (beginner-friendly, macOS/Linux/Windows) |
| Catalog analytics & search | [vast-catalog USAGE](../vast/vast-catalog/USAGE.md) |
| Capacity / DRR reporting | [vast-du README](../vast/vast-du/README.md) |
| Work-journal pipeline | [timefinder SETUP_macOS](../timefinder/SETUP_macOS.md) |

Full inventory: [Tool Index](tool-index.md).
