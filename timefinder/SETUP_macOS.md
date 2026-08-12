# TimeFinder macOS Setup

> **Platform:** TimeFinder is developed and tested on **macOS only**.

Complete this guide once, then use [README.md](README.md) for day-to-day commands. For system design, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## What you need

| Component | Required? | Notes |
|-----------|-----------|-------|
| Slack CLI + service token | **Yes** | Read channel history |
| `slack_channels.json` | **Yes** | Channel name → ID map |
| Gmail config | No | Skip for Slack-only workflow |
| Google OAuth | No | Only for `--sync-google` or live Gmail API |

**Minimum viable path:** Steps 1–3 and 5 → gather with `--slack-only` → generate → review ICS.

---

## Step 1 — Install the Slack CLI

TimeFinder uses the official **[Slack CLI](https://docs.slack.dev/tools/slack-cli/)** for authentication and token generation.

```bash
curl -fsSL https://downloads.slack-edge.com/slack-cli/install.sh | bash
```

Ensure `~/.local/bin` is on your `PATH` (add to `~/.zshrc` if needed):

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.zshrc
```

Verify:

```bash
slack --help
slack auth login          # opens browser — credentials → ~/.slack/credentials.json
slack auth list
slack api conversations.list
```

---

## Step 2 — Generate a Slack service token

TimeFinder needs a **user service token** (`xoxp-…`) to read channel history:

```bash
slack auth token
```

Copy the token — you will paste it into `slack_channels.json` in Step 3.

### Browser credentials (advanced)

Browser session tokens (`xoxc-` + `d` cookie / `xoxd-`) work for gather, discover, and `--harvest-thread`. Extract from Developer Tools → Network → `client.counts`, then save as `slack_token` / `slack_d_cookie` in `~/.timefinder_cache/slack_channels.json`. Harvest uses that same file by default (override with `--slack-config` or `--credentials` for Slack CLI team-map format).

---

## Step 3 — Configure Slack channels

Config file: **`~/.timefinder_cache/slack_channels.json`**

### Option A — Discover then add inline (recommended)

After you have a token in config (minimal shell below), run discovery for a recent week:

```bash
mkdir -p ~/.timefinder_cache
```

Create a starter config with your token:

```json
{
  "slack_token": "xoxp-your-service-token-here",
  "slack_d_cookie": "",
  "channels": {}
}
```

Then:

```bash
python3 timefinder/timefinder.py --discover-slack-channels --lookback-days 7
```

When prompted, choose **[A]dd All** or **[S]elect Individually** to write discovered channels into config — no separate resolver step required.

### Option B — Interactive resolver

```bash
python3 timefinder/timefinder.py --add-slack-channels
```

Paste your `xoxp-` token when prompted. Leave **d cookie** blank for service tokens. Resolve channel names, DMs, or group DMs, then save.

### Option C — One-shot initializer

Maps a hardcoded channel list from `channels_init.py`:

```bash
python3 timefinder/timefinder.py --init-channels
```

---

## Step 4 — Configure Gmail (optional)

Skip this step for **Slack-only** workflows (`--gather-candidate-entries --slack-only`).

When you want Gmail in gather, pick one path:

| Step | Method | When to use |
|------|--------|-------------|
| **4C** | Local import (Takeout / `.eml`) | No app passwords, no Google Cloud project |
| **4A** | IMAP app password | Personal `@gmail.com` |
| **4B** | OAuth Gmail API | You can create a Google Cloud OAuth client |

Config path: **`~/.timefinder_cache/gmail_config.json`**

---

### Step 4C — Local import (no API credentials)

#### 4C.1 Export via Google Takeout

1. Open [Google Takeout](https://takeout.google.com)
2. **Deselect all** → enable **Mail** only
3. Prefer **`.mbox`** format if offered
4. Download when the export email arrives

#### 4C.2 Import directory

```bash
mkdir -p ~/.timefinder_cache/gmail_import
# copy Inbox.mbox, Sent.mbox, or individual .eml files here
```

#### 4C.3 Config

```json
{
  "auth": "import",
  "import_dir": "~/.timefinder_cache/gmail_import"
}
```

Gather prints: `Using local Gmail import (.eml / .mbox — no API credentials).`

Re-export periodically; only messages within `--lookback-days` are read.

---

### Step 4A — IMAP app password (personal Gmail)

1. Enable [2-Step Verification](https://myaccount.google.com/security)
2. Gmail → Settings → **Enable IMAP**
3. Create password at [Google App Passwords](https://myaccount.google.com/apppasswords)

```json
{
  "auth": "imap",
  "email": "you@gmail.com",
  "app_password": "xxxx xxxx xxxx xxxx",
  "folders": ["INBOX", "[Gmail]/Sent Mail"]
}
```

---

### Step 4B — OAuth Gmail API

1. [Google Cloud Console](https://console.cloud.google.com/) → enable **Gmail API** and **Google Calendar API**
2. Create **Desktop app** OAuth client → save as `~/.timefinder_cache/google_client_secret.json`
3. Run `python3 timefinder/timefinder.py --setup-google-auth`
4. Config:

```json
{
  "auth": "oauth",
  "email": "you@your-company.com",
  "labels": ["INBOX", "SENT"]
}
```

---

## Step 5 — Python environment

```bash
cd ~/path/to/kmactools
python3 -m venv .venv
source .venv/bin/activate
pip install -r timefinder/requirements.txt
```

Google packages are only needed for OAuth gather or Calendar sync.

---

## Step 6 — Google Calendar sync (optional)

Requires OAuth (Step 4B or standalone Calendar client + `--setup-google-auth`):

```bash
python3 timefinder/timefinder.py --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.json
```

Or import `calendar_candidates.ics` manually into any calendar app.

---

## Step 7 — Verify end-to-end

```bash
source ~/path/to/kmactools/.venv/bin/activate
cd ~/path/to/kmactools

# Slack-only smoke test
python3 timefinder/timefinder.py --gather-candidate-entries --slack-only --verbose
python3 timefinder/timefinder.py --generate-candidates
open ~/.timefinder_cache/calendar_review/calendar_candidates.md
python3 timefinder/timefinder.py --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics
```

Tests:

```bash
pytest timefinder/tests/ -v
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `slack: command not found` | PATH | Add `~/.local/bin` to `~/.zshrc` |
| `invalid_auth` | Bad/expired token | `slack auth token` → update `slack_channels.json` |
| `missing_scope` on `--harvest-thread` | Token lacks `*:history` (e.g. Slack CLI login token passed via `--credentials`) | Use `xoxc-` + `xoxd-` (or an `xoxp-` with history scopes) in `~/.timefinder_cache/slack_channels.json`. Harvest defaults to that file, same as gather/discover. |
| `Slack configuration not found` | Missing config | Step 3 |
| Gmail skipped during gather | No `gmail_config.json` | Expected with `--slack-only`; add Step 4 or use `--require-gmail` to enforce |
| App passwords denied | Workspace policy | Step 4C import, or Slack-only |
| No Google Cloud project | OAuth blocked | Step 4C import, or Slack-only |
| `No .eml or .mbox files found` | Empty import dir | Refresh Takeout export |
| `Google token not found` | OAuth not run | `--setup-google-auth` or use import mode |
| `--add-slack-channels` network errors | Proxy / payload truncation | Use `--discover-slack-channels` instead — adds from scan results without extra API round-trips |
| Stale Takeout data | Old export | New Takeout run; copy into `gmail_import/` |

---

## Security

- Never commit `~/.timefinder_cache/` or tokens to git.
- Treat `xoxp-` tokens like passwords.
- Message backups may contain sensitive content — restrict directory permissions.

---

[← README](README.md) · [Architecture →](ARCHITECTURE.md)
