# VAST Toolkit

This directory contains the core specialized modules for the VAST ecosystem, ranging from authentication and identity management to disk usage analysis and stream auditing.

## Modules Overview

| Module | Purpose | Key Scripts |
| :--- | :--- | :--- |
| **[auth](./auth)** | Credential and Token Management | `vast_get_token.py` |
| **[common](./common)** | Shared Internal Utilities | `utils.py` |
| **[identity](./identity)** | AD Configuration & Identity | `show_ad_configs.py` |
| **[vast-catalog](./vast-catalog)** | Element Store catalog analytics, search, DRR, S3 tagging | `vcatalog_tool.py` |
| **[vast-db](./vast-db)** | VASTDB time-series ingest & tabular analytics | `alltick_to_vastdb.py`, `read_ticks.py` |
| **[vast-du](./vast-du)** | Data Reduction & Capacity Metrics | `vast-du.py`, `vast-entropy-sim.py` |
| **[vast-opstat](./vast-opstat)** | Live multi-protocol performance monitor (NFS v3/v4.1, NVMe-oTCP, SMB) | `vast-opstat.py` |
| **[vast-sniff](./vast-sniff)** | Network/Stream Sniffing | `vast-sniff.sh` |
| **[vast-viewer](./vast-viewer)** | VAST Viewer | `vast-viewer.py`, `audit_vast_viewer.py` |

