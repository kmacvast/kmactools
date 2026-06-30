# vast-opstat

Multi-protocol VAST performance statistics tool. Query VMS performance counters
and display live protocol operation rates, latency, throughput, and workload
classification from the terminal.

## Requirements

- Python 3.8+
- No third-party packages — stdlib only
- VAST VMS accessible over HTTPS (default port 443)

## Quick Start

```bash
cd vast/vast-opstat

# NFS v3 (implemented)
./vast-opstat.py --nfs --version=3.0 --vms <VMS_HOST> --user <USER> --password <PASS>
```

See [NFSv3_README.md](NFSv3_README.md) for NFS v3 usage, keyboard controls, and
metric details.

## Protocol Reference

| Protocol | CLI flags | Status | Documentation |
|----------|-----------|--------|---------------|
| NFS v3 | `--nfs --version=3.0` | Implemented | [NFSv3_README.md](NFSv3_README.md) |
| NFS v4.1 | `--nfs --version=4.1` | Planned | — |
| NFS v4.2 | `--nfs --version=4.2` | Planned | — |
| NVMe-oTCP | `--block --nvme-over-tcp` | Planned | — |
| SMB | `--smb` | Planned | — |

### Flag rules

- `--version` is **required** with `--nfs` (e.g. `--version=3.0`).
- `--version` is **not** used with `--smb`.
- `--block` requires `--nvme-over-tcp`.
- Use `-V` / `--tool-version` to print the vast-opstat release version.

## Shared Connection Options

These flags apply to all implemented protocols:

| Option | Default | Description |
|--------|---------|-------------|
| `--vms HOST` | — | VMS hostname or IP (required) |
| `--port N` | `443` | VMS HTTPS port |
| `--user USER` | `admin` | VMS username |
| `--password PASS` | — | VMS password (prompted if omitted) |
| `--sample-average WIN` | — | Rolling average window (e.g. `10m`, `1h`, `4h`) |
| `--refresh N` | `5` | Refresh interval in seconds |
| `--csv FILENAME` | — | Append captured samples to a CSV file |
| `--no-color` | — | Disable ANSI color output |
| `--discover-metrics` | — | Enumerate metrics and objects, then exit |

## Credits

NFS v3 monitoring logic is based on the original work of **Jeff Mohler (J-Mo)** in
`vast-nfstop.py`.

## Tests

```bash
pytest tests/test_vast_opstat.py -v
```
