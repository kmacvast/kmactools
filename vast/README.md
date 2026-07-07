# VAST Toolkit

The core modules for the VAST ecosystem — from authentication and identity through
capacity analysis, performance monitoring, and stream auditing.

> New here? See the repo [Architecture](../docs/architecture.md) and
> [Getting Started](../docs/getting-started.md). Credentials for every tool are documented
> in [docs/credentials.md](../docs/credentials.md).

## Modules

| Module | Purpose | Key scripts | Docs |
|---|---|---|---|
| **[auth](./auth)** | Credential & token management | `vast_get_token.py` | [README](./auth/README.md) |
| **[common](./common)** | Shared internal utilities | `utils.py` | [README](./common/README.md) |
| **[identity](./identity)** | AD / identity inspection | `show_ad_configs.py` | [README](./identity/README.md) |
| **[vast-catalog](./vast-catalog)** | Element Store catalog analytics, search, DRR, S3 tagging | `vcatalog_tool.py` | [README](./vast-catalog/README.md) · [USAGE](./vast-catalog/USAGE.md) |
| **[vast-db](./vast-db)** | VASTDB time-series ingest & telemetry | `alltick_to_vastdb.py`, `read_ticks.py` | [README](./vast-db/README.md) |
| **[vast-du](./vast-du)** | Data reduction & capacity metrics | `vast-du.py`, `vast-entropy-sim.py` | [README](./vast-du/README.md) |
| **[vast-opstat](./vast-opstat)** | Live multi-protocol performance monitor (NFS v3/v4.1, NVMe-oTCP, SMB) | `vast-opstat.py` | [README](./vast-opstat/README.md) · [SETUP](./vast-opstat/SETUP.md) |
| **[vast-sniff](./vast-sniff)** | Leader-node packet capture | `vast-sniff.sh` | [README](./vast-sniff/README.md) |
| **[vast-viewer](./vast-viewer)** | Read-only VAST config inspector | `vast-viewer.py`, `audit_vast_viewer.py` | [README](./vast-viewer/README.md) |
