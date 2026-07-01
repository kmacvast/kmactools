# TimeFinder

TimeFinder builds an **evidence-backed work journal** from Slack and optionally Gmail. It gathers messages locally, finds meaningful work conversations, and produces calendar entries you review before syncing to Google Calendar.

These are not fake meetings — each candidate links back to real messages.

> **Platform:** macOS only. First-time setup → **[SETUP_macOS.md](SETUP_macOS.md)**

---

## Documentation map

| If you want to… | Read |
|-----------------|------|
| Install Slack CLI, tokens, Gmail, Python venv | [SETUP_macOS.md](SETUP_macOS.md) |
| Understand modules, data flow, and auth | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Tune scoring, clustering, dedup rules | [HEURISTICS.md](HEURISTICS.md) |
| Run commands day to day | This file |

---

## Quick start (after setup)

From the repo root with your venv activated:

```bash
# 1. Find Slack channels where you posted recently (optional — adds to config inline)
./timefinder/timefinder.py --discover-slack-channels --date 2026-06-26 --lookback-days 7

# 2. Pull messages into local cache (Slack-only is fine if Gmail is not configured)
./timefinder/timefinder.py --gather-candidate-entries --lookback-days 7

# 3. Build review files from local backups
./timefinder/timefinder.py --generate-candidates --date 2026-06-26 --lookback-days 7

# 4. Review and approve
./timefinder/timefinder.py --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics

# 5. Sync approved entries (optional — requires Google OAuth)
./timefinder/timefinder.py --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.json
```

Output lands in `~/.timefinder_cache/calendar_review/`.

---

## How it works

```
configure Slack  →  gather messages  →  generate candidates  →  review  →  sync (optional)
     ↑ optional Gmail
```

1. **Configure** — `slack_channels.json` (required). Gmail is optional.
2. **Gather** — Download Slack/Gmail messages into `~/.timefinder_cache/`.
3. **Generate** — Rule-based scoring (local, no LLM) → JSON, Markdown, ICS.
4. **Review** — Approve, edit, or reject each block.
5. **Sync** — Push approved events to Google Calendar.

Deep dive: [ARCHITECTURE.md](ARCHITECTURE.md) · Scoring rules: [HEURISTICS.md](HEURISTICS.md)

---

## CLI reference

Single entry point:

```bash
./timefinder/timefinder.py [action] [options]
```

### Actions

| Flag | Purpose |
|------|---------|
| `--discover-slack-channels` | Find conversations where **you** posted in the `--date` window; optionally add untracked targets to config |
| `--init-channels` | One-shot bootstrap from a fixed channel list in code |
| `--add-slack-channels` | Interactive resolver for channel names, DMs, group DMs |
| `--gather-candidate-entries` | Fetch Slack and/or Gmail messages into cache |
| `--generate-candidates` | Build work-journal candidates from local backups |
| `--review-ics PATH` | Interactive approve / remove / modify wizard |
| `--setup-google-auth` | OAuth browser flow for Gmail API and/or Calendar |
| `--sync-google PATH` | Push approved JSON or ICS to Google Calendar |
| `--harvest-thread` | Deep export of one Slack channel + threads |

### Common options

| Flag | Default | Used by |
|------|---------|---------|
| `--date YYYY-MM-DD` | today | discover, generate |
| `--lookback-days N` | `7` | discover, gather, generate |
| `--slack-only` | off | gather — skip Gmail |
| `--require-gmail` | off | gather — fail if Gmail unavailable |
| `--verbose` | off | most commands |
| `--min-confidence` | `0.65` | generate |
| `--dry-run` | off | generate |

Full generate options: see [HEURISTICS.md](HEURISTICS.md#tunable-cli-parameters) or run with conflicting flags to print help.

---

## Typical workflows

### Slack-only (no Google credentials)

Works when OAuth and app passwords are blocked:

```bash
./timefinder/timefinder.py --discover-slack-channels --lookback-days 7
./timefinder/timefinder.py --gather-candidate-entries --slack-only --lookback-days 7
./timefinder/timefinder.py --generate-candidates --lookback-days 7
./timefinder/timefinder.py --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics
```

Import the reviewed `.ics` into any calendar app manually if Calendar sync is unavailable.

### Weekly journal with Gmail import

When you can export mail via Takeout but not use APIs:

1. Drop fresh `.mbox` files in `~/.timefinder_cache/gmail_import/` (see [SETUP_macOS.md](SETUP_macOS.md) Step 4C).
2. Gather without `--slack-only`.
3. Generate and review as above.

> **Note:** Candidate **generation** is Slack-only today. Gmail is gathered for future use and cross-reference.

### Locked date range

Use the same `--date` and `--lookback-days` on discover, gather, and generate so all stages align:

```bash
./timefinder/timefinder.py --generate-candidates --date 2026-06-26 --lookback-days 7
```

Only messages between **2026-06-19** and **2026-06-26** (inclusive) are included.

---

## Config at a glance

All paths under `~/.timefinder_cache/` — details in [ARCHITECTURE.md](ARCHITECTURE.md#data-layout-timefinder_cache).

| File | Required? | Purpose |
|------|-----------|---------|
| `slack_channels.json` | Yes | Slack token + channel map |
| `gmail_config.json` | No | Gmail import / IMAP / OAuth |
| `google_client_secret.json` | No | OAuth desktop client |
| `google_token.json` | No | Created by `--setup-google-auth` |

Minimal Slack config:

```json
{
  "slack_token": "xoxp-...",
  "slack_d_cookie": "",
  "channels": {
    "your-channel": "C01A2BCDEFG"
  }
}
```

Gmail modes (pick one): **import** (Takeout), **imap** (personal Gmail), **oauth** (API). See [SETUP_macOS.md](SETUP_macOS.md) Step 4.

---

## Review output

After `--generate-candidates`:

| File | Purpose |
|------|---------|
| `calendar_candidates.json` | Structured source of truth; set `"status": "approved"` for sync |
| `calendar_candidates.md` | Human-readable summary |
| `calendar_candidates.ics` | Import or review via `--review-ics` |

---

## Testing

```bash
pytest timefinder/tests/ -v
```

Mocked APIs only — no live Slack, Gmail, or network.

---

## Security

- Secrets stay in `~/.timefinder_cache/` — never commit that directory.
- Candidate evidence redacts obvious tokens and passwords.
- Raw backups are read-only for the pipeline.
- Scoring does not call LLM or external APIs.

---

## Planned enhancements

- Gmail-aware candidate generation
- Stronger cross-channel dedup for overlapping project threads
- Optional AI summarization (today: rules only)
