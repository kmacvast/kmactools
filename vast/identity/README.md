# identity

Identity and directory-service inspection for VAST clusters via the VMS REST API.

> Part of the [kmactools](../../docs/README.md) toolkit.

---

## `show_ad_configs.py`

Lists all Active Directory configurations on a cluster using the schema-less `vastpy`
pattern (`client.activedirectory.get()` → `GET /api/activedirectory/`). Read-only.

For each config it prints the ID, domain name, machine account, and state.

### Requirements

```bash
pip install vastpy
```

### Usage

Authentication is via an API token in the environment (VAST 5.3+):

```bash
export VMS_ADDRESS="var203.selab.vastdata.com"   # optional; defaults to a placeholder
export VMS_TOKEN="your-api-token"
python3 show_ad_configs.py
```

Generate a token with [`vast/auth/vast_get_token.py`](../auth/README.md). See
[docs/credentials.md](../../docs/credentials.md) for all credential options.

Tested by [`tests/test_show_ad_configs.py`](../../tests/test_show_ad_configs.py).
