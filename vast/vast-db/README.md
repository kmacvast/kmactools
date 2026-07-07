# vast-db

Real-time market time-series ingest and telemetry against **VASTDB**. These scripts stream
live quotes into a VASTDB table, read them back, monitor row growth, and visualize the data
in a branded dashboard.

> Part of the [kmactools](../../docs/README.md) toolkit. See the
> [VAST dual control planes](../../docs/architecture.md#the-vast-dual-control-planes) for
> how the VASTDB data plane fits in.

---

## Scripts

| Script | Purpose |
|---|---|
| `alltick_to_vastdb.py` | Connect to the AllTick websocket feed and micro-batch quotes into a VASTDB table (flush on 1,000 rows or every 2s). |
| `read_ticks.py` | Read/query recent tick records back out of VASTDB. |
| `mon_vastdb_records.py` | Live monitor of row count / capacity using cyclic ACID snapshot transactions and PyArrow metadata scans. |
| `chart_creator.py` | Streamlit + Plotly dashboard rendering stored ticks with a VAST-themed UI. |

---

## Requirements

```bash
pip install vastdb pyarrow pandas websocket-client plotly streamlit
```

---

## Configuration

All scripts read a single JSON file at `~/.vast-ingestor`:

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

```bash
chmod 600 ~/.vast-ingestor
```

See [docs/credentials.md](../../docs/credentials.md) for all config files used across the
repo.

---

## Usage

```bash
# Stream live quotes into VASTDB (Ctrl-C to stop)
python3 alltick_to_vastdb.py

# Read recent ticks back
python3 read_ticks.py

# Live row-count / capacity monitor
python3 mon_vastdb_records.py

# Launch the telemetry dashboard
streamlit run chart_creator.py
```

---

**Author:** KMac · kmac@vastdata.com
