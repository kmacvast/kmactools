# VAST Toolkit

This directory contains the core specialized modules for the VAST ecosystem, ranging from authentication and identity management to disk usage analysis and stream auditing.

## Modules Overview

| Module | Purpose | Key Scripts |
| :--- | :--- | :--- |
| **[auth](./auth)** | Credential and Token Management | `vast_get_token.py` |
| **[common](./common)** | Shared Internal Utilities | `utils.py` |
| **[identity](./identity)** | Ad Configuration & Identity | `show_ad_configs.py` |
| **[vast-du](./vast-du)** | Data Reduction & Capacity Metrics | `vast-du.py`, `vast-entropy-sim.py` |
| **[vast-sniff](./vast-sniff)** | Network/Stream Sniffing | `vast-sniff.sh` |
| **[vast-viewer](./vast-viewer)** | VAST Viewer | `vast-viewer.py`, `audit_vast_viewer.py` |

