# Credentials

Different modules in this repo were built at different times and use different credential
files. This page is the single reference for all of them. **Never hardcode IPs, users,
passwords, or tokens** — always load them from one of the files below and `chmod 600` it.

---

## Config file matrix

| File | Used by | Format |
|---|---|---|
| `~/.vastconf` | `vast-opstat`, `vast-du`, `auth`, `common` (shared loader) | JSON |
| `~/.vast-catalog-config.json` | `vast-catalog` (`vcatalog_tool.py`) | JSON |
| `~/.vast-viewer.conf` | `vast-viewer` | JSON |
| `~/.vast-ingestor` | `vast-db` ingest/telemetry scripts | JSON |
| `VMS_TOKEN` env var | `identity/show_ad_configs.py` | environment |
| `VAST_PASSWORD` / `VAST_TOKEN` env vars | `vast-opstat` (preferred over `--password`) | environment |

> **Roadmap note:** consolidating these onto the shared `~/.vastconf` loader
> (`vast/common/utils.py`) is desirable but out of scope for the docs refactor. Until
> then, treat this table as authoritative.

---

## `~/.vastconf` (shared VMS loader)

Loaded by `vast/common/utils.py::load_vast_config()`, which expands `~` and normalizes the
`tenant` field: a blank or `"default"` tenant becomes `None` to support Global-Admin auth.

```json
{
  "vms": "var203.selab.vastdata.com",
  "user": "admin",
  "tenant": "default",
  "password": "YOUR_PASSWORD"
}
```

```bash
chmod 600 ~/.vastconf
```

- `token` may be supplied instead of `password` for VAST 5.3+ token auth.
- `tenant`: use `"default"` (or omit) for Global Admin; set a tenant name for tenant-scoped
  auth.

---

## `~/.vast-catalog-config.json` (vast-catalog)

`vcatalog_tool.py` needs both the VASTDB data endpoint and the VMS REST endpoint.

```json
{
  "vastdb_endpoint": "http://vip-pool.lab:80",
  "vastdb_access_key": "…",
  "vastdb_secret_key": "…",
  "vms_address": "var203.selab.vastdata.com",
  "vms_user": "admin",
  "vms_password": "YOUR_PASSWORD"
}
```

See [vast-catalog/USAGE.md](../vast/vast-catalog/USAGE.md) for the authoritative schema and
optional fields (`vms_token`, bucket/schema defaults, etc.).

---

## `~/.vast-viewer.conf` (vast-viewer)

```json
{
  "vast_server": "snake.lab.vastdata.com",
  "vast_user": "superman",
  "vast_passwd": "kryptonite"
}
```

CLI flags (`--server`, `--user`, `--password`) override the file.

---

## `~/.vast-ingestor` (vast-db)

Used by the VASTDB market-data ingest and telemetry scripts.

```json
{
  "VAST_ENDPOINT": "http://vip-pool.lab:80",
  "VAST_ACCESS_KEY": "…",
  "VAST_SECRET_KEY": "…",
  "VAST_BUCKET": "market-data",
  "VAST_SCHEMA": "ticks",
  "VAST_TABLE_NAME": "trades",
  "ALLTICK_TOKEN": "…"
}
```

---

## Getting an API token

Token auth is safer than storing passwords. Generate one from `~/.vastconf`:

```bash
python3 vast/auth/vast_get_token.py
```

See [auth/README.md](../vast/auth/README.md). For `vast-opstat`, prefer exporting
`VAST_TOKEN` / `VAST_PASSWORD` (or use the interactive wizard's secure prompt) instead of
passing `--password` on the command line, which is visible in `ps` and shell history.
