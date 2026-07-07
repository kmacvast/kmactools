# VAST Catalog Unified Admin Tool (`vast-catalog`)

**Version:** 1.3.7 · **Engine:** `vcatalog_tool.py` · **Author:** KMac kmac@vastdata.com

---

## Project Vision & Executive Overview

`vcatalog_tool.py` is a unified, production-ready administrative and demo-delivery engine for the VAST Element Store. It consolidates twelve legacy lab scripts into a single CLI that queries metadata, audits capacity, governs quotas, mutates S3 tags, and educates customers on Global Data Reduction—all without touching the filesystem tree.

| Legacy approach | `vcatalog_tool.py` approach |
|---|---|
| `find /mnt/export -name '*.JPEG'` — walks every directory inode | `--search --ext JPEG --limit 10` — Ibis predicate pushed into VASTDB |
| `du -sh /mnt/export/workspace_1` — recursive stat crawl | `--show-capacity` — streams catalog `size`/`used` columns in parallel batches |
| Manual VMS GUI clicks for quota/capacity | `--update-quotas`, `--show-data-reduction-rates` — REST via `vastpy` |

The tool **never crawls the filesystem**. Every catalog mode opens a VASTDB session, projects only the columns it needs, and applies server-side filters through Ibis expressions that compile to database pushdown. Results return in sub-second to low-second time even at **44M+ indexed files** (550+ PyArrow record batches in lab profiles). POSIX paths appear only where a mode must bridge NFS mount coordinates to catalog logical paths or S3 object keys.

For every flag, example command, console layout, and configuration field, see **[USAGE.md](./USAGE.md)**.

---

## Core Architectural Framework & Lifecycle Mechanics

### Dual-Lens Paradigm

The engine operates across two complementary control planes:

#### 1. VAST Catalog Plane (VASTDB)

- **Transport:** `vastdb.connect()` with endpoint, access key, and secret from `~/.vast-catalog-config.json`.
- **Query layer:** Ibis column expressions (`ibis_col.parent_path.startswith(...)`, timestamp windows, ownership filters) compile to server-side predicates.
- **Streaming:** PyArrow `RecordBatchReader.read_next_batch()` yields chunks; the tool never materializes the full catalog into RAM.
- **Transaction lifecycle:** `_catalog_transaction()` wraps `session.transaction()`, suppressing benign `MissingTransaction` warnings on early-exit search paths.

Typical flow:

```
CLI args → build_context() → connect_catalog()
         → session.transaction() → tx.catalog().select(columns, predicate)
         → RecordBatch stream → fold/merge or display
```

#### 2. VMS REST Control Plane

- **Transport:** `vastpy.VASTClient` authenticated from the same JSON config (`vms_address`, `vms_user`, `vms_password` or `vms_token`).
- **Endpoints used:**
  - `GET /api/capacity/?path=…` — logical, unique, usable byte tiers
  - `GET /api/quotas/?path=…` — inode counts and quota consumption
  - `POST /api/quotas/` — workspace quota registration (`--update-quotas`)
- **CLI bridge:** `vastpy-cli` subprocess for quota matrix display when password auth is required.

### Parallel Stream Processing Optimization Layer

Analytics modes (`--show-capacity`, `--show-cold-files`, `--analysis-by-owner`) use `_parallel_catalog_aggregate()`:

- The **main thread** streams batches from VASTDB (single reader, single transaction).
- A **ThreadPoolExecutor** (up to **32 workers**, scaled by `min(32, cpu_count × 2)`) folds each batch into partial metrics in worker threads.
- A thread-safe **merge function** accumulates results into a shared dataclass accumulator (`CapacityAccumulator`, `ColdFilesAccumulator`, `SecurityAccumulator`).
- Client RAM stays flat because only one batch is in flight per fold cycle; workers process numeric summaries, not full namespace copies.

Search modes with client-side filters (`--sparse`) use a different optimization: **early-exit streaming** closes the PyArrow reader as soon as `--limit` matches are collected, completing in milliseconds on multi-million-file namespaces.

---

## VAST Metaspace Glossary

| Term | Catalog / API field | Meaning |
|---|---|---|
| **Logical capacity** | `size` (catalog), `used_effective_capacity` (quota) | Bytes applications believe they wrote—pre-reduction. |
| **Physical / Usable capacity** | `used` (catalog), `usable` (capacity API), `used_capacity` (quota) | Bytes actually occupied on NVMe after inline Global Data Reduction. |
| **Unique capacity** | `unique` (capacity API) | Post-dedup/similarity footprint attributable to a path; space reclaimable if the directory is deleted. |
| **Data Reduction Ratio (DRR)** | computed | Logical ÷ Physical. A 4:1 DRR means 1 PB of flash holds 4 PB of logical customer data. |
| **Global Block Deduplication** | pillar 1 | Cluster-wide elimination of identical blocks. |
| **Global Similarity Clustering** | pillar 2 | Near-duplicate content clustered into shared chunks (VM images, genomics slices, log batches). |
| **Data Stream Compression** | pillar 3 | Per-stream LZ4/Huffman compression after dedup/similarity stages. |
| **phandle** | `phandle["handle_id"]` | VAST internal file pointer struct; replaces traditional Unix inode integers in catalog queries (`--inode`). |
| **parent_path** | catalog column | Logical namespace prefix (`/tenant/export/...`); maps 1:1 to NFS mount paths and S3 key prefixes. |

---

## Repository Architecture Blueprint

```
kmactools/
├── tests/
│   ├── test_vcatalog_tool.py          # Canonical mock regression suite (no live VMS)
│   └── test_vcatalog_cyberdemo.py     # Cyber-demo script tests
└── vast/vast-catalog/
    ├── vcatalog_tool.py               # Master unified CLI engine (v1.3.7)
    ├── vcatalog_cyberdemo.py          # Cyber-demo variant
    ├── find_files_nfs.py              # NFS find helper (superseded by catalog search)
    ├── run_vcat_test_suite.sh         # Live integration harness
    ├── vast-catalog-config.example.json
    ├── requirements.txt               # Python dependencies (vastdb, pyarrow, boto3, …)
    ├── README.md                      # ← You are here (architecture & vision)
    ├── USAGE.md                       # Full CLI manual, flags, and output mockups
    └── ALGORITHM.md                   # Internal algorithm notes
```

**Execution entry point:**

```bash
cd vast/vast-catalog
chmod +x vcatalog_tool.py
./vcatalog_tool.py --about
```

---

## Deep-Dive Usage Redirection

This document explains *why* and *how* the tool is architected. For operational detail—credential setup, every CLI flag, mode-by-mode console layouts, search recipes, and harness commands—open:

### → **[USAGE.md — Full Command Reference & Operational Manual](./USAGE.md)**

Quick starting points from that manual:

| Task | Command |
|---|---|
| Platform education guide | `./vcatalog_tool.py --about` |
| Capacity histogram | `./vcatalog_tool.py --show-capacity` |
| Sparse-file search (early exit) | `./vcatalog_tool.py --search --sparse --limit 5` |
| Multi-pillar DRR dashboard | `./vcatalog_tool.py --show-data-reduction-rates --directory workspace_1` |
| Run mock unit tests | `pytest tests/test_vcatalog_tool.py` (from repo root) |
| Run live integration harness | `./run_vcat_test_suite.sh` (from this directory) |

---

## Related Documentation

- [`vast-catalog-config.example.json`](./vast-catalog-config.example.json) — credential template
- [`ALGORITHM.md`](./ALGORITHM.md) — streaming fold/merge internals
- [`../../.cursor/rules/vast-config-standard.mdc`](../../.cursor/rules/vast-config-standard.mdc) — lab credential conventions
