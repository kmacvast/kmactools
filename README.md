# kmactools

**Solutions Engineering Diagnostic, Automation, and Systems Interrogation Toolkit**

An optimized workspace for VAST Data Solutions Engineering: storage-fabric profiling,
catalog-scale metadata analytics, communication-intelligence harvesting, and lab
diagnostics. Built for repeatable lab workflows, customer-facing demos, and fast
root-cause analysis.

![kmactools repository architecture](docs/images/repo-architecture.png)

---

## Start here

| I want to… | Go to |
|---|---|
| Understand the repo and how it's organized | [docs/architecture.md](docs/architecture.md) |
| Install and run my first command | [docs/getting-started.md](docs/getting-started.md) |
| Configure cluster credentials | [docs/credentials.md](docs/credentials.md) |
| Run the tests | [docs/testing.md](docs/testing.md) |
| Find a specific tool or script | [docs/tool-index.md](docs/tool-index.md) |
| Browse all documentation | [docs/README.md](docs/README.md) |

---

## The three pillars

| Pillar | Path | Focus |
|---|---|---|
| **Storage-fabric engineering** | [`vast/`](vast/) | Catalog analytics, capacity/DRR, VMS auth, multi-protocol performance monitoring, config auditing |
| **Communication intelligence** | [`timefinder/`](timefinder/) | Local Slack/Gmail harvesting → work-journal candidates → Google Calendar |
| **Infrastructure diagnostics** | [`scripts/`](scripts/) | macOS scopes, virtualization debuggers, transcription, lab harnesses |

Each module ships its own README next to the code; the [docs/](docs/) hub holds the
cross-cutting guides.

---

## 60-second quickstart

```bash
git clone git@github.com:kmacvast/kmactools.git
cd kmactools
python3 -m venv .venv && source .venv/bin/activate

# Live multi-protocol performance monitor (interactive — no flags needed)
./vast/vast-opstat/vast-opstat.py

# Catalog platform education (no credentials needed)
./vast/vast-catalog/vcatalog_tool.py --about

# Mocked regression suite
pip install pytest pytest-mock && pytest tests/
```

Full setup: [docs/getting-started.md](docs/getting-started.md).

---

## Highlighted tools

- **[vast-catalog](vast/vast-catalog/README.md)** — parallel streaming catalog analytics,
  early-exit search, DRR dashboards, S3 tagging (never crawls the filesystem).
- **[vast-opstat](vast/vast-opstat/README.md)** — live NFS v3 / NFS v4.1 / NVMe-oTCP / SMB
  performance dashboard, stdlib-only, with an interactive setup wizard.
- **[timefinder](timefinder/README.md)** — evidence-backed work journal from Slack/Gmail.

---

## License

Licensed under the terms of the [LICENSE](LICENSE) file.

**Maintainer:** KMac · kmac@vastdata.com
