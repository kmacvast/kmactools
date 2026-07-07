# common

Shared internal utilities for the `vast/` toolkit. Import from here instead of
re-implementing config loading in each script.

> Part of the [kmactools](../../docs/README.md) toolkit.

---

## `utils.py`

### `load_vast_config(path="~/.vastconf") -> dict`

Loads and normalizes the shared VMS config file. This is the **mandatory** way VMS tools
obtain connection details — do not re-implement it.

What it handles:

- Expands `~` in the path and raises `FileNotFoundError` if the file is missing.
- Parses the JSON config.
- **Tenant normalization:** a blank or `"default"` tenant is set to `None` so Global-Admin
  auth works; a real tenant name is preserved for tenant-scoped auth.
- Calls `urllib3.disable_warnings()` to silence self-signed-cert warnings in the lab.

Returns the config dict (`vms`, `user`, `password`/`token`, `tenant`, …).

---

## Usage

```python
from vast.common.utils import load_vast_config

conf = load_vast_config()          # reads ~/.vastconf
client = VASTClient(
    address=conf["vms"],
    token=conf.get("token"),       # prefer token; fall back to user/password
    user=conf.get("user"),
    password=conf.get("password"),
    tenant_name=conf.get("tenant"),
)
```

Config file format and the full credential matrix:
[docs/credentials.md](../../docs/credentials.md).

Tested by [`tests/test_utils.py`](../../tests/test_utils.py).
