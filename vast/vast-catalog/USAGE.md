# VAST Catalog Tool — Operational Manual

**Module:** `vast/vast-catalog/vcatalog_tool.py` · **Version:** 1.3.7

This document is the exhaustive technical reference for installing, configuring, and operating the unified VAST Catalog administration CLI. For architectural context and the VAST platform glossary, see **[README.md](./README.md)**.

---

## Prerequisites & Lab Configuration Ingestion

### System Requirements

| Requirement | Notes |
|---|---|
| Python | 3.10+ recommended |
| VASTDB access | Catalog endpoint + access/secret keys |
| VMS access | For quota and DRR modes (`vastpy`, `vastpy-cli`) |
| NFS mount | Optional; required for path translation and S3 tag targets |
| Dependencies | Install from [`requirements.txt`](./requirements.txt) |

```bash
pip install -r requirements.txt
# Also required at runtime: vastpy (VMS REST), ibis (catalog predicates)
```

### Credential File: `~/.vast-catalog-config.json`

All modes read **one** JSON file (override with `--config`). Copy the template:

```bash
cp vast-catalog-config.example.json ~/.vast-catalog-config.json
chmod 600 ~/.vast-catalog-config.json
```

#### Full schema

| Key | Required by | Description |
|---|---|---|
| `vast_endpoint` | Catalog modes | VASTDB HTTPS endpoint |
| `access_key` | Catalog modes | VASTDB access key |
| `secret_key` | Catalog modes | VASTDB secret key |
| `vms_address` | VMS modes | VMS hostname (legacy alias: `vms`) |
| `vms_user` | VMS modes | VMS username (default: `admin`; alias: `user`) |
| `vms_password` | VMS modes | VMS password (alias: `password`) |
| `vms_token` | VMS modes (optional) | Long-lived API token from `vast_get_token.py`; alternative to password for `--show-data-reduction-rates` |
| `tenant` | VMS modes | Tenant name; blank or `"default"` → Global Admin |
| `mount_path` | Path translation, S3 tags | NFS client mount (default: `/mnt/kmacs-root/vast-catalog`) |
| `bucket_name` | S3 URI translation | S3 bucket for object-key mapping |
| `catalog_prefix` | All catalog scans | Logical catalog root (default: `/kmacs/vast-catalog`) |

#### Example

```json
{
  "vast_endpoint": "https://vast-vms-hostname",
  "access_key": "YOUR_VASTDB_ACCESS_KEY",
  "secret_key": "YOUR_VASTDB_SECRET_KEY",
  "vms_address": "var202.selab.vastdata.com",
  "vms_user": "admin",
  "vms_password": "YOUR_VMS_PASSWORD",
  "vms_token": null,
  "tenant": null,
  "mount_path": "/mnt/kmacs-root/vast-catalog",
  "bucket_name": "kmacs-vast-catalog-test-bucket",
  "catalog_prefix": "/kmacs/vast-catalog"
}
```

Password resolution order for VMS: `--vms-password` → `VMS_PASSWORD` env → `vms_password` in config → interactive prompt.

---

## Command-Line Interface Flag Matrix

One **mutually exclusive core mode** is required per invocation (except `--about`, which pre-parses and exits before mode validation).

### Global Modifiers

| Flag | Default | Description |
|---|---|---|
| `--config PATH` | `~/.vast-catalog-config.json` | Alternate credential file |
| `--catalog-prefix PATH` | config / `/kmacs/vast-catalog` | Logical subtree for catalog queries |
| `--mount-path PATH` | config / `/mnt/kmacs-root/vast-catalog` | NFS mount override |
| `--directory PATH` | catalog prefix | Repeatable target for `--show-data-reduction-rates` |

### Mutually Exclusive Core Modes

| Mode | Purpose |
|---|---|
| `--show-capacity` | 4-tier size histogram + logical/physical totals |
| `--show-cold-files` | Retention audit + waste scrap detection |
| `--analysis-by-owner` | Owner consumption + world-writable (`o+w`) audit |
| `--update-quotas` | Register workspace quotas; print allocation matrix |
| `--search` | Multi-dimensional metadata search |
| `--show-schema` | Print catalog Arrow schema columns |
| `--translate-path PATH` | NFS ↔ catalog ↔ S3 coordinate matrix |
| `--show-data-reduction-rates` | VMS multi-pillar DRR dashboard |
| `--seed-baseline` | Download Linux 2.6.11 kernel tarball seed |
| `--seed-bulk` | Clone Enron + Tiny-ImageNet workspaces |
| `--copy-infinitely` | Dictionary-driven infinite copy loop (lab stress) |
| `--add-s3-tag KEY=VALUE` | Put S3 object tag (requires `--s3-target`) |
| `--modify-s3-tag KEY=VALUE` | Modify existing S3 tag |
| `--delete-s3-tag KEY` | Delete S3 tag key |

### Mode-Specific Options

| Flag | Modes | Default | Description |
|---|---|---|---|
| `--num-days N` | `--show-cold-files` | 365 | Cold-data age threshold |
| `--uid N` | `--analysis-by-owner`, `--search` | — | Filter to POSIX UID |
| `--brief` | `--update-quotas` | off | Skip registration banners; matrix only |
| `--vms-password SECRET` | `--update-quotas`, `--show-data-reduction-rates` | — | VMS password override |
| `--copies N` | `--seed-bulk` | 5 | Workspace clone count |
| `--dataset-url URL` | `--seed-baseline` | kernel.org tarball | Baseline download URL |
| `--s3-target PATH` | S3 tag modes | — | Absolute NFS path to target object |

### Search / Filter Attributes (with `--search`)

| Flag | Pushdown | Description |
|---|---|---|
| `--name STR` | server | Name substring (`contains`) |
| `--ext STR` | server | File extension (leading `. optional) |
| `--type file\|dir` | server | Element type |
| `--user STR` | server | POSIX owner name |
| `--group STR` | server | POSIX group (`group_owner_name`) |
| `--gid N` | server | Numeric GID |
| `--mode OCTAL` | server | Exact `nfs_mode_bits` |
| `--min-size SIZE` | server | Minimum logical size (`10M`, `2G`, …) |
| `--min-physical SIZE` | server | Minimum physical `used` bytes |
| `--sparse` | **client** | Logical > physical (Global Reduction benefit) |
| `--mmin N` | server | Modified within N minutes |
| `--amin N` | server | Accessed within N minutes |
| `--cmin N` | server | Changed within N minutes |
| `--crmin N` | server | Created within N minutes |
| `--depth N` | server | Exact path depth (schema-dependent) |
| `--links N` | server | Hard link count |
| `--inode N` | server | `phandle["handle_id"]` lookup |
| `--limit N` | display / early exit | Max rows shown; `0` = unlimited (default: 20) |

### Reference Flags

| Flag | Description |
|---|---|
| `-h`, `--help` | Argparse quick reference + examples |
| `--about` | Customer-facing VAST platform education guide (no mode required) |

---

## Operational Mode Breakdown & Console Layouts

### Capacity Profile Dashboard (`--show-capacity`)

**Calculates:** Total logical (`size`) vs physical (`used`) bytes across all FILE elements under `--catalog-prefix`, plus a 4-tier structural histogram.

**Pushdown:** `parent_path.startswith(catalog_prefix)`.

**Parallelism:** Batches folded across up to 32 worker threads; main thread streams VASTDB.

**Tier boundaries:**

| Tier | Size range |
|---|---|
| Tiny (< 4KB - Metadata Inlined) | `< 4096 B` |
| Small (4KB to 64KB) | `4096 B – 64 KB` |
| Medium (64KB to 1MB) | `64 KB – 1 MB` |
| Large (> 1MB) | `> 1 MB` |

**Example output:**

```
========================================================================================
  CAPACITY PROFILE & DATA STRUCTURE
========================================================================================

  Catalog prefix         /kmacs/vast-catalog
  Global logical size    2.41 TB
  Global physical used   612.18 GB
  Net block delta        1.81 TB

  4-Tier Size Histogram

  Tiny (< 4KB - Metadata Inlined)
    Files     : 38,412,901
    Logical   : 89.12 GB  |  Physical : 41.03 GB
  ────────────────────────────────────────────────────────────
  Small (4KB to 64KB)
    Files     : 4,102,331
    Logical   : 112.44 GB  |  Physical : 88.21 GB
  ...
```

---

### Retention & Waste Audit (`--show-cold-files`)

**Calculates:** Files older than `--num-days` (default 365) by catalog `mtime`, plus orphaned scrap files matching extensions `.tmp`, `.bak`, `.log` or waste name patterns (`session`, `cache`, `build_scratch`, …).

**Pushdown:** Streaming scan under catalog prefix; cold/waste rules evaluated per batch.

**Example:**

```bash
./vcatalog_tool.py --show-cold-files --num-days 180
```

**Example output:**

```
========================================================================================
  DATA RETENTION & EFFICIENCY ANALYSIS
========================================================================================

  Catalog prefix         /kmacs/vast-catalog
  Cold threshold         180 days
  Total files            46,218,442
  Total footprint        2.41 TB

  Rule 1 — Cold data (>180 days unmodified)
    Count : 12,441,002   Volume : 891.22 GB

  Rule 2 — Orphaned scraps (.tmp, .bak, .log)
    Count : 18,204         Volume : 4.12 GB

  Summary
    Waste candidates : 12,459,206 files / 895.34 GB
    Optimal footprint: 1.52 TB
    Efficiency ratio : 62.91%
```

---

### POSIX Compliance & Governance Audit (`--analysis-by-owner`)

**Calculates:** Per-owner logical byte totals (`owner_name`, `uid`) and lists world-writable files (`nfs_mode_bits` with other-write bit set).

**Optional filter:** `--uid 1000` scopes to one identity.

**Example output:**

```
========================================================================================
  SECURITY & OWNERSHIP AUDIT
========================================================================================

  Owner                  UID        Files          Logical Mass
  ──────────────────────────────────────────────────────────────────────
  vastdata               1000       18,442,901     1.12 TB
  research               1001       4,102,331      412.18 GB
  ...

  World-writable exposures: 42 files (o+w)

  Sample exposures (up to 5):
  [666] debug_dump.tmp              workspace_3/scratch/debug_dump.tmp
```

---

### Multi-Pillar Data Reduction Deep-Dive (`--show-data-reduction-rates`)

**Data sources:** `GET /api/capacity/` + `GET /api/quotas/` via `vastpy`.

**Math:**

1. **Global DRR** = logical ÷ usable (physical).
2. **Compression savings** = `(unique − usable) / logical` — measured directly from capacity tiers.
3. **Dedup + Similarity savings** = `(logical − unique) / logical`, apportioned:
   - Deduplication: **40%** of pre-compression savings
   - Similarity: **35%** of pre-compression savings
   - (Remaining 25% weight reserved in tier model; compression reported separately)

**Example:**

```bash
./vcatalog_tool.py --show-data-reduction-rates \
  --directory /kmacs/vast-catalog/workspace_1 \
  --directory workspace_2
```

**Example output:**

```
========================================================================================
                 VAST CLUSTER: MULTI-FACTOR DATA REDUCTION DEEP DIVE
========================================================================================
 Data Sources: GET /api/capacity/ + GET /api/quotas/
 Target Scope Directory : /kmacs/vast-catalog/workspace_1
 Active File Elements   : 2,441,002 files profiled (quota inodes)
 Total Logical Mass     : 412.18 GB
 Unique Post-Dedup Mass : 98.44 GB
 Net Physical Footprint  : 82.11 GB
 Global Reduction Ratio : 5.02:1
========================================================================================
 CAPACITY TIER SUMMARY:
 ────────────────────────────────────────────────────────────────────────────────────────
  Tier                         Capacity         Stage Ratio      Space Reclaimed
 ────────────────────────────────────────────────────────────────────────────────────────
  Logical (Written)            412.18 GB        —                —
  Unique (Dedup + Similarity)  98.44 GB         4.19:1           40.00% + 35.00%
  Physical (Usable)            82.11 GB         1.20:1           5.00%
 ...
 INDEPENDENT STORAGE REDUCTION RATES:
 [ Pillar 1 ] Global Block Deduplication Savings : 40.00% Space Reclaimed
 [ Pillar 2 ] Global Similarity Clustering Savings: 35.00% Space Reclaimed
 [ Pillar 3 ] Global Data Stream Compression Savings: 5.00% Space Reclaimed
 ...
 Net Cluster Savings Overhead: 80.08% Total Data Reduction
```

---

### Cross-Protocol Translation Matrix (`--translate-path`)

**Maps:** A single input path (NFS mount, catalog logical, or relative) to three coordinate systems using `mount_path`, `catalog_prefix`, and `bucket_name` from config.

**Example:**

```bash
./vcatalog_tool.py --translate-path /mnt/kmacs-root/vast-catalog/workspace_1/model.bin
```

**Example output:**

```
========================================================================================
                 VAST PROTOCOL PATH TRANSLATION MATRIX
========================================================================================
 NFS Local Client Mount : /mnt/kmacs-root/vast-catalog/workspace_1/model.bin
 VAST Catalog DB Logic  : /kmacs/vast-catalog/workspace_1/model.bin
 S3 Bucket Object Key   : s3://kmacs-vast-catalog-test-bucket/workspace_1/model.bin
========================================================================================
```

---

### Quota Registration (`--update-quotas`)

**Actions:** POST workspace directory quotas via `vastpy-cli`, wait 3 s for aggregation, print inode/capacity matrix.

```bash
./vcatalog_tool.py --update-quotas --brief --vms-password '$SECRET'
```

---

### Multi-Protocol S3 Tag Mutations

Requires `--s3-target` with an **absolute NFS path** under the configured mount. Uses `boto3` against the VAST S3 endpoint.

| Mode | Syntax | Example |
|---|---|---|
| Add | `--add-s3-tag KEY=VALUE` | `--add-s3-tag 'project=demo' --s3-target /mnt/.../file.bin` |
| Modify | `--modify-s3-tag KEY=VALUE` | `--modify-s3-tag 'project=prod' --s3-target /mnt/.../file.bin` |
| Delete | `--delete-s3-tag KEY` | `--delete-s3-tag project --s3-target /mnt/.../file.bin` |

---

### Catalog Schema Introspection (`--show-schema`)

Prints Arrow schema column names and types from a live catalog transaction—useful for verifying field names before writing search predicates.

---

### Lab Seeding Modes

| Mode | Description |
|---|---|
| `--seed-baseline` | Downloads Linux 2.6.11 tarball to mount; injects dummy waste files |
| `--seed-bulk [--copies N]` | Enron mail + Tiny-ImageNet into numbered `workspace_*` dirs |
| `--copy-infinitely` | Stress loop copying dictionary words (SIGINT to stop) |

---

## Advanced Search Strategies & Early-Exit Stream Optimization

### Server-side vs client-side filters

Most search predicates compile to Ibis expressions and execute inside VASTDB. **`--sparse`** is the exception: it requires comparing two columns (`size > used`) and runs as a **client-side pandas filter** on each streamed batch.

When `--sparse` combines with `--limit N`:

1. Server streams all FILE rows matching other server predicates (typically just catalog prefix).
2. Client applies `df["size"] > df["used"]` per batch.
3. On reaching `N` matches, the PyArrow reader is **closed inside the transaction**.
4. `_catalog_transaction()` suppresses benign `MissingTransaction` cleanup warnings.

### Real-world combination examples

```bash
# Early-exit sparse search — sub-second on 44M+ files
./vcatalog_tool.py --search --sparse --limit 5

# Extension + owner + recency (all server-side)
./vcatalog_tool.py --search --ext locked --user vastdata --type file --mmin 1440 --limit 10

# Large logical files with aggressive reduction
./vcatalog_tool.py --search --min-size 10G --sparse --limit 20

# Security review — world-readable pattern
./vcatalog_tool.py --search --mode 666 --limit 50

# Internal handle lookup
./vcatalog_tool.py --search --inode 18446744073709551615 --limit 1
```

**Example search output:**

```
========================================================================================
  CATALOG METADATA SEARCH
========================================================================================

  Query time : 0.3621 s
  Matches    : 5  (first 5, scan stopped early shown)

  TYPE   OWNER      GROUP      NAME                             LOGICAL    PHYSICAL
  ────────────────────────────────────────────────────────────────────────────────────────
  FILE   vastdata   staff      genome_slice_0042.bin            4.88 GB    1.12 GB
  FILE   research   scientists vm_template_v3.qcow2            12.00 GB   2.44 GB
  ...
```

---

## Harness Verification & Unit Testing Framework

### Mock regression suite (no live VMS / VASTDB)

From the **repository root**:

```bash
python3 -m unittest tests.test_vcatalog_tool -v
```

Or from this directory (legacy path):

```bash
python3 -m unittest test_vcatalog_tool.py
```

The canonical suite (`tests/test_vcatalog_tool.py`) includes **48 mocked tests** covering:

- Byte formatting and path translation
- DRR pillar math
- Parallel batch aggregation
- Sparse search early-exit and `MissingTransaction` suppression
- VMS credential normalization
- Argparse routing

### Live integration harness

From `vast/vast-catalog/` with credentials configured and NFS mount reachable:

```bash
chmod +x vcatalog_tool.py run_vcat_test_suite.sh
./run_vcat_test_suite.sh
```

**11 integration stages:**

| # | Stage |
|---|---|
| 1 | Python unittest regression |
| 2 | `--about` platform guide |
| 3 | `--show-schema` |
| 4 | `--show-capacity` |
| 5 | `--show-cold-files --num-days 180` |
| 6 | `--analysis-by-owner --uid 1000` |
| 7 | `--show-data-reduction-rates --directory workspace_1` |
| 8 | `--translate-path` (dynamic sample file) |
| 9 | S3 tag add/modify/delete lifecycle (dynamic sample file) |
| 10 | `--search --sparse --limit 5` |
| 11 | `--search --ext locked --mmin 1440 --user vastdata --type file --limit 5` |

The harness calls `resolve_sample_file()` to locate a readable file under `/mnt/kmacs-root/vast-catalog` before Tests 8–9; stages are skipped with a warning if the mount is empty.

---

## Quick Reference Card

```bash
# Education
./vcatalog_tool.py --about

# Analytics (catalog plane)
./vcatalog_tool.py --show-capacity
./vcatalog_tool.py --show-cold-files --num-days 90
./vcatalog_tool.py --analysis-by-owner

# Governance (VMS plane)
./vcatalog_tool.py --update-quotas --brief
./vcatalog_tool.py --show-data-reduction-rates --directory workspace_1

# Search
./vcatalog_tool.py --search --sparse --limit 5

# Cross-protocol
./vcatalog_tool.py --translate-path /mnt/kmacs-root/vast-catalog/workspace_1/file.bin
```

---

**See also:** [README.md](./README.md) · [vast-catalog-config.example.json](./vast-catalog-config.example.json) · [ALGORITHM.md](./ALGORITHM.md)
