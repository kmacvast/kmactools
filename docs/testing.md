# Testing

The repository uses **pytest**. The root [`tests/`](../tests/) suite is fully mocked — it
never touches a live VMS. Dependency-heavy suites are skipped automatically when their
third-party packages are absent, so `pytest tests/` stays green even on a stdlib-only venv.

---

## Run the suite

```bash
# From the repository root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Minimal: stdlib-only suites (opstat, tui_layout, utils, …)
pip install pytest pytest-mock
pytest tests/

# Full matrix (adds vastdb/pyarrow/pandas/boto3/… backed suites)
pip install -r dev-requirements.txt
pytest tests/
```

> The older `python3 -m unittest discover -s tests` command **does not** work for these
> suites — they rely on pytest fixtures (`capsys`, `monkeypatch`). Always use `pytest`.

TimeFinder has its own suite:

```bash
pytest timefinder/tests/ -v
```

---

## What's covered

| Test file | Covers | Extra deps |
|---|---|---|
| `test_vast_opstat.py` | vast-opstat engines, CLI dispatch, wizard, telemetry math, monitor lifecycle, OS-version header, audit regressions | stdlib |
| `test_tui_layout.py` | Shared TUI helpers: column sizing, ANSI width/truncation, formatters, glyphs | stdlib |
| `test_utils.py` | `vast/common/utils.py` — `load_vast_config()` tenant normalization | stdlib |
| `test_vast_viewer.py` | vast-viewer output formatting + config resolution (mocked `vastpy`) | stdlib |
| `test_audit_vast_viewer.py` | viewer audit wrapper | stdlib |
| `test_show_ad_configs.py` | identity AD config listing (mocked `vastpy`) | stdlib |
| `test_vast_get_token.py` | auth token generation (mocked `vastpy`) | stdlib |
| `test_find_files_nfs.py` | catalog NFS find helper | stdlib |
| `test_smb_phase0_discover.py` | SMB Phase 0 discovery probe | stdlib |
| `test_vast_entropy_sim.py` | vast-du entropy simulator | stdlib |
| `test_vcatalog_tool.py` | vcatalog_tool streaming search, DRR math, parallel aggregation, credentials, argparse | `vastdb`, `pyarrow`, `pandas`, `boto3` |
| `test_vcatalog_cyberdemo.py` | cyber-demo script behavior | `pandas` |
| `test_vast_du.py` | vast-du capacity metric / config logic | `vastpy` |

`test_vcatalog_tool.py` and `test_vast_du.py` use `pytest.importorskip`, so they skip
cleanly when their dependencies aren't installed.

---

## Live integration harnesses

Some checks require lab credentials and a reachable cluster/NFS mount, e.g.:

```bash
cd vast/vast-catalog && ./run_vcat_test_suite.sh
```

These are **not** part of the mocked `pytest tests/` run.
