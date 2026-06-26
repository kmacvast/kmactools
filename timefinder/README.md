# TimeFinder

TimeFinder builds a work journal from your Slack and Gmail activity. It gathers local message backups, identifies meaningful work conversations, and produces reviewable calendar entries you can approve before syncing to Google Calendar.

These are not fake meetings. They are evidence-backed work-journal blocks derived from real messages.

> **macOS only.** First-time setup: see **[SETUP_macOS.md](SETUP_macOS.md)** (Slack CLI install, `slack auth token`, config).

## How it works

```
init/add channels  →  gather entries  →  generate candidates  →  review ICS  →  sync Google
```

1. **Configure** Slack channels and Gmail IMAP credentials (both required).
2. **Gather** messages into `~/.timefinder_cache/`.
3. **Generate** calendar candidate files for human review.
4. **Review** candidates interactively with `--review-ics` or edit JSON/Markdown manually.
5. **Sync** approved entries to Google Calendar with `--sync-google`.

## Architecture

Candidate generation is **100% local and rule-based** — no LLMs, no network calls during scoring. TimeFinder loads Slack backups from disk, clusters conversations, scores them with weighted heuristics (participants, threads, keywords, ticket IDs, channel context), deduplicates overlapping work across channels, and writes reviewable calendar files.

For the full pipeline — noise filtering, clustering windows, scoring table, Jaccard dedup, and time normalization — see **[HEURISTICS.md](HEURISTICS.md)**.

## Unified CLI

All capabilities are exposed through a single entry point:

```bash
./timefinder/timefinder.py [capability flag] [options]
```

| Flag | Purpose |
|------|---------|
| `--init-channels` | One-shot bootstrap: map a hardcoded channel list to Slack IDs |
| `--add-slack-channels` | Interactive resolver for channels, DMs, and group DMs |
| `--gather-candidate-entries` | Gather Slack and Gmail messages (both required) |
| `--generate-candidates` | Generate work-journal calendar candidates from local backups |
| `--harvest-thread` | Harvest all messages and thread replies from a Slack channel |
| `--review-ics PATH` | Interactive wizard to approve, remove, or modify ICS entries |
| `--setup-google-auth` | Run Google OAuth2 browser flow; save token to cache |
| `--sync-google PATH` | Push approved JSON or reviewed ICS events to Google Calendar |

### Library modules

| Module | Purpose |
|--------|---------|
| `slack_messages.py` | Slack API fetch, thread replies, user name map |
| `gmail_messages.py` | Gmail IMAP fetch and normalization |
| `candidates.py` | Rule-based candidate generation engine |
| `ics_review.py` | Interactive ICS review wizard |
| `google_auth.py` | Shared Google OAuth (Gmail + Calendar) |
| `google_calendar.py` | Google Calendar sync |
| `thread_harvest.py` | Full channel + thread JSON harvest |
| `channels_init.py` | Slack channel bootstrap |
| `channels_resolve.py` | Interactive Slack target resolver |
| `message_gather.py` | Slack/Gmail backup orchestration |

## Directory layout

```
timefinder/
├── README.md
├── SETUP_macOS.md
├── HEURISTICS.md
├── requirements.txt
├── timefinder.py
├── slack_messages.py
├── gmail_messages.py
├── candidates.py
├── ics_review.py
├── google_calendar.py
├── thread_harvest.py
├── channels_init.py
├── channels_resolve.py
├── message_gather.py
└── tests/
    ├── fixtures/
    └── test_*.py
```

## Cache and config (`~/.timefinder_cache/`)

| Path | Description |
|------|-------------|
| `slack_channels.json` | Slack token, session cookie, channel name → ID map |
| `gmail_config.json` | Gmail IMAP credentials and folder list |
| `slack_users.json` | Slack user ID → display name map (auto-updated) |
| `google_client_secret.json` | Google OAuth desktop client credentials (you provide) |
| `google_token.json` | Google OAuth token (created by `--setup-google-auth`) |
| `slack_{channel}_{date}.json` | Slack message backups |
| `gmail_{folder}_{date}.json` | Gmail message backups |
| `calendar_review/` | Generated candidate review files |

### Slack config example

`~/.timefinder_cache/slack_channels.json`:

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

### Gmail config (required)

TimeFinder supports two Gmail auth modes:

| Mode | Best for | Config |
|------|----------|--------|
| **`oauth`** (recommended) | **Google Workspace** (`@vastdata.com`) when app passwords are disabled | OAuth via `--setup-google-auth` |
| **`imap`** | Personal `@gmail.com` accounts | App-specific password |

Config path: `~/.timefinder_cache/gmail_config.json`

#### Option A — OAuth (Google Workspace / `@vastdata.com`)

Use this when app passwords are blocked by your org (common on Workspace).

1. In [Google Cloud Console](https://console.cloud.google.com/):
   - Create or select a project
   - Enable **Gmail API** and **Google Calendar API**
   - Configure OAuth consent screen (Internal if `@vastdata.com` only)
   - Create **Desktop app** OAuth credentials
   - Download JSON → save as `~/.timefinder_cache/google_client_secret.json`

2. Authorize TimeFinder (browser flow — Gmail read + Calendar write):

```bash
./timefinder/timefinder.py --setup-google-auth
```

3. Create `~/.timefinder_cache/gmail_config.json`:

```json
{
  "auth": "oauth",
  "email": "kevin.mcdonald@vastdata.com",
  "labels": ["INBOX", "SENT"]
}
```

`labels` accepts Gmail API label IDs (`INBOX`, `SENT`, `DRAFT`, …) or IMAP-style names like `[Gmail]/Sent Mail`.

Full Workspace walkthrough: **[SETUP_macOS.md](SETUP_macOS.md)** Step 4B.

#### Option B — IMAP app password (personal Gmail)

```json
{
  "auth": "imap",
  "email": "you@gmail.com",
  "app_password": "your-16-char-app-password",
  "folders": ["INBOX", "[Gmail]/Sent Mail"]
}
```

**App password setup** (consumer Gmail only):

1. Enable [2-Step Verification](https://myaccount.google.com/security)
2. Enable IMAP: Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP
3. Generate password at [Google App Passwords](https://myaccount.google.com/apppasswords)
4. Paste the 16-character password into `gmail_config.json`

Full IMAP walkthrough: **[SETUP_macOS.md](SETUP_macOS.md)** Step 4A.

## Setup

**New users:** complete **[SETUP_macOS.md](SETUP_macOS.md)** first (Slack CLI, `slack auth token`, Python venv).

Install Google API dependencies (required for Workspace Gmail OAuth and Calendar sync):

```bash
pip install -r timefinder/requirements.txt
```

### Google OAuth (Gmail + Calendar)

One `--setup-google-auth` run authorizes both Gmail read access and Calendar write access. Required for Workspace Gmail; also used for `--sync-google`.

1. Enable **Gmail API** and **Google Calendar API** in Google Cloud Console.
2. Download OAuth **Desktop app** credentials → `~/.timefinder_cache/google_client_secret.json`.
3. Run:

```bash
./timefinder/timefinder.py --setup-google-auth
```

Token saved to `~/.timefinder_cache/google_token.json`.

## Usage

Run from the repo root:

```bash
cd ~/git/kmactools
```

### Initialize Slack channels

```bash
./timefinder/timefinder.py --init-channels
./timefinder/timefinder.py --add-slack-channels
```

### Gather messages

Both Slack and Gmail must be configured. The gather step fails if either source errors.

```bash
# Slack + Gmail (required)
./timefinder/timefinder.py --gather-candidate-entries

# Options
./timefinder/timefinder.py --gather-candidate-entries --lookback-days 7 --verbose
```

If Gmail is not configured, see **[SETUP_macOS.md](SETUP_macOS.md)** — Step 4B for Workspace OAuth, Step 4A for personal IMAP.

### Generate calendar candidates

```bash
./timefinder/timefinder.py --generate-candidates
./timefinder/timefinder.py --generate-candidates --date 2026-06-22
./timefinder/timefinder.py --generate-candidates --min-confidence 0.65
./timefinder/timefinder.py --generate-candidates --dry-run --verbose
./timefinder/timefinder.py --generate-candidates --include-trivial-debug
./timefinder/timefinder.py --generate-candidates --no-ics
```

#### `--generate-candidates` options

| Flag | Default | Description |
|------|---------|-------------|
| `--input-dir` | `~/.timefinder_cache` | Slack backup input directory |
| `--output-dir` | `~/.timefinder_cache/calendar_review` | Review output directory |
| `--user-map` | `~/.timefinder_cache/slack_users.json` | Slack user display name map |
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

### Harvest a Slack channel

```bash
./timefinder/timefinder.py --harvest-thread --channel C0123456789
./timefinder/timefinder.py --harvest-thread -c C0123456789 -o ~/Downloads/slack_C0123456789.json
```

Uses `~/.slack/credentials.json` by default (browser session tokens).

### Review output

After running `--generate-candidates`:

| File | Purpose |
|------|---------|
| `calendar_candidates.json` | Authoritative structured output |
| `calendar_candidates.md` | Human-readable review |
| `calendar_candidates.ics` | Importable calendar file |

Every candidate starts with `"status": "pending_review"`. Edit JSON to set `"approved"` or `"rejected"`.

### Interactive ICS review

```bash
./timefinder/timefinder.py --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics
```

For each `VEVENT`, choose **[A]pprove**, **[R]emove**, **[M]odify**, or **[S]kip**. Modifications prompt for title, start time, and end time. Changes are written atomically after the full loop completes.

### Sync to Google Calendar

Mark candidates `"approved"` in JSON, or review via ICS first, then:

```bash
./timefinder/timefinder.py --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.json
./timefinder/timefinder.py --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.ics
```

Events are inserted into your default `primary` Google Calendar.

## Typical weekly workflow

TimeFinder defaults to a 7-day lookback, so a once-per-week run is a natural cadence:

```bash
./timefinder/timefinder.py --gather-candidate-entries
./timefinder/timefinder.py --generate-candidates
./timefinder/timefinder.py --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics
# mark approved in JSON if syncing from JSON
./timefinder/timefinder.py --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.json
```

## Testing

Tests live in `timefinder/tests/`. Run from the repo root:

```bash
pytest timefinder/tests/ -v
```

Fixtures are in `timefinder/tests/fixtures/`. Tests use mocked HTTP/IMAP/Google API — no live Slack, Gmail, or network calls.

## Security

- Tokens, cookies, and passwords stay in local config files under `~/.timefinder_cache/`.
- Candidate output redacts obvious secrets from evidence excerpts.
- Raw backup files are never modified.
- v1 candidate scoring does not call LLM APIs.
- Google Calendar sync uses OAuth2 with locally stored tokens.

## Planned enhancements

- Cap duration correctly after cross-channel dedup merge
- Improve dedup for overlapping project-channel workstreams
- Gmail-aware candidate generation (currently Slack-only for candidates)
- Optional AI summarization/classification
