# VAST Viewer

This is a simple VAST viewer built on top of the [vastpy](https://github.com/vast-data/vastpy) module. Instead of using `vcli` and fighting through unstructured output, I wanted something that returned clean JSON I could easily pipe into `jq` and other tooling.

The goal is to simplify repetitive read-only VAST inspection tasks with cleaner, more predictable output. This tool does not perform write operations and cannot modify or destroy cluster configuration.

Creds to Bryan G for introducing me to [vastpy](https://github.com/vast-data/vastpy).

## Components

* **`vast-viewer.py`**: Primary CLI tool for VAST resource inspection.
* **`audit_vast_viewer.py`**: Wrapper script that validates the main script after new features are added so we don't accidentally break stuff.
* **`test_vast_viewer.py`**: Pytest-based test suite for CLI reliability and regression testing.

---

## Authentication

To interact with the VAST API, the tools require valid credentials. You can authenticate using one of the following methods.

### 1. Super secret hidden credential file

Store credentials in `~/.vast-viewer.conf` for convenience and re-use.

```bash
$ cat ~/.vast-viewer.conf

{
    "vast_server": "snake.lab.vastdata.com",
    "vast_user": "superman",
    "vast_passwd": "kryptonite"
}
```

### 2. Command-line parameters

You can also specify or override credentials directly on the command line.

```bash
--server SERVER       VAST VMS IP/Hostname
--user USER           VAST User
--password PASSWORD   VAST Password
```

---

## Usage: `vast-viewer.py`

The viewer allows you to inspect specific resources by ID or list resources across the cluster.

```bash
$ python3 vast-viewer.py

usage: vast-viewer.py [-h] [--server SERVER] [--user USER]
                      [--password PASSWORD]
                      [--output {text,json,csv,table}]
                      [--list-policies] [--list-views]
                      [--list-tenants] [--list-vippools]
                      [--list-activities] [--list-vastdns]
                      [--list-providers]
                      [--view-policy] [--view]
                      [--view-tenant] [--view-vippools]
                      [--view-activity]
                      [--view-vastdns]
                      [--view-providers]
                      [--id ID]

VAST Configuration Viewer
```

## Basic Commands

### View a specific Policy

```bash
python3 vast-viewer.py --view-policy --id <policy_id>
```

### Inspect a Tenant

```bash
python3 vast-viewer.py --view-tenant --id <tenant_id>
```

### Check VIP Pools

```bash
python3 vast-viewer.py --view-vippools --id <pool_id>
```

### Monitor Activity

```bash
python3 vast-viewer.py --view-activity --id <activity_id>
```

---

## Output Formatting

Use the `--output` flag to switch between human-readable summaries and raw structured output.

```bash
python3 vast-viewer.py --view --id 123 --output json
```

Supported formats:

* `json` (default)
* `text`
* `csv`
* `table`

JSON is the default because `jq` exists and life is short. 😄

---

## Development & Testing

PRs, suggestions, and improvements are welcome. If you find something dumb, broken, or missing, feel free to open an issue or submit a PR.