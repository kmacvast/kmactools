# AlibiGen

AlibiGen ("Alibi Generator") builds a work journal from your Slack and Gmail activity. It gathers local message backups, identifies meaningful work conversations, and produces reviewable calendar entries you can approve before anything is added to Google Calendar.

These are not fake meetings. They are evidence-backed work-journal blocks derived from real messages.

> **macOS only.** First-time setup: see **[SETUP_macOS.md](SETUP_macOS.md)** (Slack CLI install, `slack auth token`, config).

## How it works

```
resolve/init channels  →  get messages  →  get candidates  →  manual review  →  ICS import
```

1. **Configure** Slack channels (and optionally Gmail folders).
2. **Gather** messages into `~/.alibigen_cache/`.
3. **Generate** calendar candidate files for human review.
4. **Review** candidates in Markdown or JSON; mark approved/rejected.
5. **Import** `calendar_candidates.ics` into Google Calendar (manual adjustments expected).

## Scripts

Naming convention: `{verb}_alibigen_{purpose}.py`

| Script | Purpose |
|--------|---------|
| `init_alibigen_channels.py` | One-shot bootstrap: map a hardcoded channel list to Slack IDs |
| `resolve_alibigen_channels.py` | Interactive resolver for channels, DMs, and group DMs |
| `get_alibigen_messages.py` | Gather Slack and/or Gmail messages (default: both) |
| `get_alibigen_candidates.py` | Generate work-journal calendar candidates from local backups |

### Library modules

| Module | Purpose |
|--------|---------|
| `slack_messages.py` | Slack API fetch, thread replies, user name map |
| `gmail_messages.py` | Gmail IMAP fetch and normalization |

## Directory layout

```
alibigen/
├── README.md
├── SETUP_macOS.md
├── init_alibigen_channels.py
├── resolve_alibigen_channels.py
├── get_alibigen_messages.py
├── get_alibigen_candidates.py
├── slack_messages.py
├── gmail_messages.py
└── tests/
    ├── fixtures/
    └── test_*.py
```

## Cache and config (`~/.alibigen_cache/`)

| Path | Description |
|------|-------------|
| `slack_channels.json` | Slack token, session cookie, channel name → ID map |
| `gmail_config.json` | Gmail IMAP credentials and folder list |
| `slack_users.json` | Slack user ID → display name map (auto-updated) |
| `slack_{channel}_{date}.json` | Slack message backups |
| `gmail_{folder}_{date}.json` | Gmail message backups |
| `calendar_review/` | Generated candidate review files |

### Slack config example

`~/.alibigen_cache/slack_channels.json`:

```json
{
  "slack_token": "xoxp-...",
  "slack_d_cookie": "",
  "channels": {
    "your-workgroups-channel": "C01A2BCDEFG",
    "a-quick-special-project-channel": "C02A2BCDEFG"
  }
}
```

Obtain `slack_token` via `slack auth token` — see **[SETUP_macOS.md](SETUP_macOS.md)**.

### Gmail config example

`~/.alibigen_cache/gmail_config.json`:

```json
{
  "email": "you@gmail.com",
  "app_password": "your-app-specific-password",
  "folders": ["INBOX", "[Gmail]/Sent Mail"]
}
```

Use a [Google App Password](https://myaccount.google.com/apppasswords) with IMAP enabled.

## Setup

**New users:** complete **[SETUP_macOS.md](SETUP_macOS.md)** first (Slack CLI, `slack auth token`, Python venv).

### 1. Initial Slack channel config

Quick bootstrap with a fixed channel list:

```bash
~/git/kmactools/alibigen/init_alibigen_channels.py
```

Or interactively resolve channels, people, and group DMs:

```bash
~/git/kmactools/alibigen/resolve_alibigen_channels.py
```

### 2. Gmail config (optional)

Create `~/.alibigen_cache/gmail_config.json` as shown above.

## Usage

Run from the repo root or call scripts directly:

```bash
cd ~/git/kmactools
```

### Gather messages

```bash
# Slack + Gmail (default)
./alibigen/get_alibigen_messages.py

# Slack only
./alibigen/get_alibigen_messages.py --slack

# Gmail only
./alibigen/get_alibigen_messages.py --gmail

# Options
./alibigen/get_alibigen_messages.py --lookback-days 7 --verbose
```

If one source is misconfigured, the other still runs and the missing source is skipped with a message.

### Generate calendar candidates

```bash
./alibigen/get_alibigen_candidates.py
./alibigen/get_alibigen_candidates.py --date 2026-06-22
./alibigen/get_alibigen_candidates.py --min-confidence 0.65
./alibigen/get_alibigen_candidates.py --dry-run --verbose
./alibigen/get_alibigen_candidates.py --include-trivial-debug
./alibigen/get_alibigen_candidates.py --no-ics
```

#### `get_alibigen_candidates.py` options

| Flag | Default | Description |
|------|---------|-------------|
| `--input-dir` | `~/.alibigen_cache` | Slack backup input directory |
| `--output-dir` | `~/.alibigen_cache/calendar_review` | Review output directory |
| `--user-map` | `~/.alibigen_cache/slack_users.json` | Slack user display name map |
| `--lookback-days` | `7` | Days of history to consider |
| `--cluster-window-minutes` | `60` | Time window for grouping non-threaded messages |
| `--min-confidence` | `0.65` | Minimum score to include a candidate |
| `--min-duration` | `15` | Minimum event duration (minutes) |
| `--max-duration` | `120` | Maximum event duration (minutes) |
| `--date` | today | Reference date for deterministic runs |
| `--dry-run` | off | Print summary without writing files |
| `--verbose` | off | INFO logging to stderr |
| `--debug` | off | DEBUG logging (redacted excerpts only) |
| `--no-ics` | off | Skip ICS output |
| `--include-trivial-debug` | off | Write excluded groups to `trivial_excluded.json` |

### Review output

After running `get_alibigen_candidates.py`:

| File | Purpose |
|------|---------|
| `calendar_candidates.json` | Authoritative structured output |
| `calendar_candidates.md` | Human-readable review |
| `calendar_candidates.ics` | Optional import into a calendar app |

Every candidate starts with `"status": "pending_review"`. Edit JSON manually to set `"approved"` or `"rejected"`.

### Import to Google Calendar

Google Calendar import via ICS is **tested and working**. There is no direct API integration yet — import the generated file manually.

1. Review and edit candidates in `calendar_candidates.md` or `calendar_candidates.json`.
2. Optionally remove or edit entries before import (titles, times, duration).
3. Import the ICS file:
   - Google Calendar → **Settings** → **Import & export** → **Import**
   - Select `~/.alibigen_cache/calendar_review/calendar_candidates.ics`
   - Choose the target calendar (recommend a dedicated work-journal calendar)
4. **Expect manual adjustments** after import — titles, durations, and overlapping entries may need cleanup in Google Calendar.

Tips from live testing:

- Review overlapping Houdini / project-channel entries before import; dedup is good but not perfect.
- Some merged entries can exceed the 120-minute cap — trim those in Google Calendar after import.
- DM-based entries may have generic titles; rename to match how you want the journal to read.
- Import into a separate calendar first if you want to delete or rework the batch easily.

## Typical weekly workflow

AlibiGen defaults to a 7-day lookback, so a once-per-week run is a natural cadence:

```bash
./alibigen/get_alibigen_messages.py --slack
./alibigen/get_alibigen_candidates.py
open ~/.alibigen_cache/calendar_review/calendar_candidates.md
# review, edit JSON if needed, then import calendar_candidates.ics into Google Calendar
```

## Testing

Tests live in `alibigen/tests/`. Run from the repo root:

```bash
pytest alibigen/tests/ -v
```

Fixtures are in `alibigen/tests/fixtures/`. Tests use mocked HTTP/IMAP — no live Slack, Gmail, or network calls.

## Security

- Tokens, cookies, and passwords stay in local config files under `~/.alibigen_cache/`.
- Candidate output redacts obvious secrets from evidence excerpts.
- Raw backup files are never modified.
- v1 does not call LLM APIs or use the Google Calendar API directly.
- Calendar import is manual via ICS only.

## Planned enhancements

- Cap duration correctly after cross-channel dedup merge
- Improve dedup for overlapping project-channel workstreams
- `apply_alibigen_candidates.py` — direct Google Calendar API push for approved entries
- Gmail-aware candidate generation (currently Slack-only for candidates)
- Optional AI summarization/classification
- Interactive approve/reject CLI
