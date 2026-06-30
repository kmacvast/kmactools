# vast-opstat

Multi-protocol VAST performance statistics tool. Query VMS performance counters and
display live protocol operation rates, latency, throughput, and workload classification
from the terminal.

Supports **cluster-wide** and **multi-volume scoping** for block storage, plus **host
initiator metrics** drill-down for NVMe-oTCP workloads.

![vast-opstat NVMe-oTCP](images/vast-opstat.png)

---

## Getting Started & Setup

**New to Python?** Follow the step-by-step guide:

**[SETUP.md — Install Python, create a virtual environment, and run vast-opstat](SETUP.md)**

Runtime dependencies: [requirements.txt](requirements.txt) (stdlib only — no pip packages
required for execution).

---

## Quick Start

```bash
cd vast/vast-opstat

# NVMe-oTCP block — cluster-wide
./vast-opstat.py --block --nvme-over-tcp --vms <VMS_HOST> --user <USER>

# NVMe-oTCP via SSH tunnel (Teleport / zero-trust)
./vast-opstat.py --block --nvme-over-tcp --vms localhost --vms-port 8443 --user <USER>

# NVMe-oTCP block — scoped to one or more volumes
./vast-opstat.py --block --nvme-over-tcp --vms <VMS_HOST> \
  --volumes vol1,vol2 --user <USER>

# NFS v3
./vast-opstat.py --nfs --version=3.0 --vms <VMS_HOST> --user <USER>
```

---

## Protocol Reference

| Protocol | CLI flags | Status | Documentation |
|----------|-----------|--------|---------------|
| **NVMe-oTCP** | `--block --nvme-over-tcp` | **Fully Implemented** | **[NVMe_TCP_README.md](NVMe_TCP_README.md)** |
| NFS v3 | `--nfs --version=3.0` | Implemented | [NFSv3_README.md](NFSv3_README.md) |
| NFS v4.1 | `--nfs --version=4.1` | Planned | — |
| NFS v4.2 | `--nfs --version=4.2` | Planned | — |
| SMB | `--smb` | Planned | — |

### Flag rules

- `--block` requires `--nvme-over-tcp`.
- `--volume NAME` or `--volumes a,b,c` scope NVMe-oTCP stats to named volumes (optional).
- `--version` is **required** with `--nfs` (e.g. `--version=3.0`).
- `--version` is **not** used with `--smb`.
- Use `-V` / `--tool-version` to print the vast-opstat release version.

---

## Features by Protocol

### NVMe-oTCP (block)

- Cluster-wide or multi-volume scoping (`--volume` / `--volumes`)
- Hybrid volume mode: per-volume read/write via `VolumeMetrics`; reclaim, fabric, and admin ops via cluster `BlockMetrics` supplement monitors
- Counter-delta IOPS engine (true real-time rates, not lifetime counters)
- Three-panel TUI: Block Health & Workload, Performance Insights, Operations table
- Interactive drill-down: host initiators (`h`), VIP paths (`v`), cNode paths (`c`)
- CSV export and metric discovery mode

See **[NVMe_TCP_README.md](NVMe_TCP_README.md)** for CLI syntax, metric calculations,
keybinds, and architecture.

### NFS v3

- Live NFS operation rates, latency, and workload classification
- VIP and cNode path drill-down

See [NFSv3_README.md](NFSv3_README.md).

---

## Shared Connection Options

These flags apply to all implemented protocols:

| Option | Default | Description |
|--------|---------|-------------|
| `--vms HOST` | — | VMS hostname or IP (required) |
| `--vms-port PORT` | `443` | VMS HTTPS port (`--port` accepted as legacy alias) |
| `--user USER` | `admin` | VMS username |
| `--password PASS` | — | VMS password (prompted if omitted) |
| `--sample-average WIN` | — | Rolling average window (e.g. `10m`, `1h`, `4h`) |
| `--refresh N` | `5` | Refresh interval in seconds |
| `--csv FILENAME` | — | Append captured samples to a CSV file |
| `--no-color` | — | Disable ANSI color output |
| `--discover-metrics` | — | Enumerate metrics and objects, then exit |
| `--log-api-calls` | — | Log VMS REST API traffic to `/tmp/vast-opstat-api-*.log` |

### Remote clusters via SSH tunnel (Teleport / zero-trust)

When VMS is reachable only through a forwarded local port (common with Teleport,
bastion hops, or zero-trust access), point `--vms` at the tunnel endpoint and pass
the forwarded port with `--vms-port`:

```bash
# Terminal 1 — forward local 8443 to remote VMS HTTPS (443)
ssh -L 8443:var203.selab.vastdata.com:443 user@jump-host

# Terminal 2 — opstat via the tunnel
./vast-opstat.py --nfs --version=3.0 --vms localhost --vms-port 8443 --user admin
```

NVMe-oTCP-only scoping flags:

| Option | Description |
|--------|-------------|
| `--volume NAME` | Limit block stats to one volume |
| `--volumes a,b,c` | Comma-separated volume names |

### API call logging

Pass `--log-api-calls` to record every VMS HTTPS request and response to a file under
`/tmp`. The log path is printed on startup:

```
API call logging enabled: /tmp/vast-opstat-api-nvme-tcp-var203.selab.vastdata.com-443-12345.log
```

Each line includes the HTTP method, full URL, elapsed time, status code, and a
truncated response body. Authorization headers and passwords are never written to
the log. Useful for debugging monitor creation, metric availability, and tunnel
connectivity issues.

---

## Requirements

- Python 3.8+
- No third-party runtime packages (see [requirements.txt](requirements.txt))
- VAST VMS accessible over HTTPS (default port 443)

---

## Credits

NFS v3 monitoring logic is based on the original work of **Jeff Mohler (J-Mo)** in
`vast-nfstop.py`.

---

## Tests

From the repository root:

```bash
pip install pytest pytest-mock   # one-time, for development
pytest tests/test_vast_opstat.py -v
```
