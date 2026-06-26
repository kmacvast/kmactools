# TimeFinder macOS Environment Setup

> **Platform:** TimeFinder is developed and tested on **macOS only**.
> It could be ported to Windows if someone wants to do that work — this author has no Windows workstations for development. macOS > Windows.

Complete this guide before running TimeFinder. When finished, return to [README.md](README.md) for day-to-day usage.

---

## Step 1 — Install and configure the Slack CLI

TimeFinder uses the **[Slack CLI](https://docs.slack.dev/tools/slack-cli/)** — an open-source command-line tool from Slack for creating, managing, and interacting with Slack apps and workspace APIs from your terminal.

We did not build the Slack CLI. Credit and thanks to the Slack developer platform team for maintaining it. Install and authenticate it as described below; TimeFinder then uses it for setup tasks like generating a service token and verifying API access.

The Slack CLI is used to authenticate, generate a service token for TimeFinder, resolve channel IDs, and verify API access.

### 1. Installation command

Install using the official Slack CLI bootstrap script:

```bash
curl -fsSL https://downloads.slack-edge.com/slack-cli/install.sh | bash
```

### 2. What this command does

- **Downloads and executes** the latest Slack CLI release package.
- **Installs binaries** into a hidden directory in your home path:
  - `~/.slack/bin/slack`
- **Creates a symlink** at `~/.local/bin/slack` pointing to the main executable.

Ensure `~/.local/bin` is on your `PATH`. Add to `~/.zshrc` if needed:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Reload your shell:

```bash
source ~/.zshrc
```

Verify the symlink:

```bash
ls -l ~/.local/bin/slack
# should point to ~/.slack/bin/slack
```

### 3. Authentication

Log in to your workspace:

```bash
slack auth login
```

This opens a browser window to authorize the CLI. Credentials are stored in `~/.slack/credentials.json`.

### 4. Verification

```bash
slack --help
slack auth list
```

Test API access:

```bash
slack api conversations.list
```

If these commands succeed, the Slack CLI is installed and authenticated.

---

## Step 2 — Generate a Slack service token (for TimeFinder)

TimeFinder needs a **user service token** to read channel history. The easiest way to get one is through the Slack CLI — no browser dev tools required.

### Browser credentials (for thread harvest)

For `--harvest-thread`, high-privilege browser session credentials (`xoxc` tokens and `xoxd` cookies) may be required. Extract them from your browser Developer Tools Network tab (`client.counts` request) and save to `~/.slack/credentials.json`. See the thread harvest section in [README.md](README.md).

---

## Step 3 — Save credentials for TimeFinder

TimeFinder stores automation credentials in:

**`~/.timefinder_cache/slack_channels.json`**

### Option A — Interactive setup (recommended)

```bash
cd ~/path/to/kmactools
python3 timefinder/timefinder.py --add-slack-channels
```

When prompted:

- **Token** → paste the `xoxp-...` service token from Step 2
- **d cookie** → press Enter to skip (not needed for `xoxp-` tokens)

Resolve the channels, DMs, or group DMs you want to track, then save when prompted.

Or use the one-shot initializer (fixed channel list in `channels_init.py`):

```bash
python3 timefinder/timefinder.py --init-channels
```

### Option B — Manual config file

```bash
mkdir -p ~/.timefinder_cache
```

Create `~/.timefinder_cache/slack_channels.json`:

```json
{
  "slack_token": "xoxp-your-service-token-here",
  "slack_d_cookie": "",
  "channels": {}
}
```

Then run `--add-slack-channels` to populate the `channels` map, or add channel name → ID pairs manually.

---

## Step 4 — Configure Gmail (required)

TimeFinder **requires** Gmail alongside Slack. Choose **4B for Google Workspace** (`@vastdata.com`) — app passwords are often disabled by org policy.

Config path: **`~/.timefinder_cache/gmail_config.json`**

---

### Step 4A — IMAP app password (personal `@gmail.com` only)

Skip this if you are on Google Workspace and app passwords are denied.

#### 4A.1 Enable 2-Step Verification

1. Open [Google Account → Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification**

#### 4A.2 Enable IMAP

1. Gmail → **Settings** → **See all settings** → **Forwarding and POP/IMAP**
2. **Enable IMAP** → **Save Changes**

#### 4A.3 Generate app password

1. Open [Google App Passwords](https://myaccount.google.com/apppasswords)
2. Create a password for **Mail** / **Mac** (or custom name `TimeFinder`)
3. Copy the 16-character password

#### 4A.4 Create config

```json
{
  "auth": "imap",
  "email": "you@gmail.com",
  "app_password": "xxxx xxxx xxxx xxxx",
  "folders": ["INBOX", "[Gmail]/Sent Mail"]
}
```

---

### Step 4B — OAuth Gmail API (Google Workspace — recommended for `@vastdata.com`)

Use this when [App Passwords](https://myaccount.google.com/apppasswords) shows **access denied** or the option is missing. TimeFinder uses the **Gmail API** with the same OAuth token as Google Calendar sync.

#### 4B.1 Google Cloud project

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create or select a project (personal project is fine)
3. **APIs & Services → Library** → enable:
   - **Gmail API**
   - **Google Calendar API**

#### 4B.2 OAuth consent screen

1. **APIs & Services → OAuth consent screen**
2. User type: **Internal** (if available for `@vastdata.com`) or **External**
3. Add scopes (or they are requested at auth time):
   - `.../auth/gmail.readonly`
   - `.../auth/calendar.events`
4. Add your `@vastdata.com` address as a test user if using External + testing mode

> If your Workspace admin blocks third-party apps, ask them to allow your OAuth client or use an admin-approved internal app.

#### 4B.3 Desktop OAuth credentials

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type: **Desktop app**
3. Download JSON → save as:

```bash
mkdir -p ~/.timefinder_cache
# save downloaded file as:
# ~/.timefinder_cache/google_client_secret.json
```

#### 4B.4 Authorize TimeFinder

```bash
cd ~/path/to/kmactools
source .venv/bin/activate   # if using venv
python3 timefinder/timefinder.py --setup-google-auth
```

Browser opens → sign in as `kevin.mcdonald@vastdata.com` → grant access.

Token saved to `~/.timefinder_cache/google_token.json`.

#### 4B.5 Create `gmail_config.json`

```json
{
  "auth": "oauth",
  "email": "kevin.mcdonald@vastdata.com",
  "labels": ["INBOX", "SENT"]
}
```

| Field | Notes |
|-------|-------|
| `auth` | Must be `"oauth"` |
| `email` | Your Workspace address (informational) |
| `labels` | Gmail label IDs: `INBOX`, `SENT`, `DRAFT`, `STARRED`, etc. IMAP names like `[Gmail]/Sent Mail` also work |

#### 4B.6 Verify (optional)

```bash
python3 timefinder/timefinder.py --gather-candidate-entries --verbose
```

You should see: `Using Gmail API (OAuth) — recommended for Google Workspace.`

---

## Step 5 — Python environment (macOS)

From the repo root:

```bash
cd ~/path/to/kmactools
python3 -m venv .venv
source .venv/bin/activate
pip install -r timefinder/requirements.txt
```

---

## Step 6 — Google Calendar sync (optional)

If you completed Step 4B, OAuth is already configured. To push approved work-journal entries to Calendar:

```bash
python3 timefinder/timefinder.py --sync-google ~/.timefinder_cache/calendar_review/calendar_candidates.json
```

If you skipped 4B and only need Calendar sync (not Workspace Gmail), enable Calendar API, save `google_client_secret.json`, and run `--setup-google-auth`.

## Step 7 — Verify TimeFinder end-to-end

```bash
source ~/path/to/kmactools/.venv/bin/activate
cd ~/path/to/kmactools

python3 timefinder/timefinder.py --gather-candidate-entries
python3 timefinder/timefinder.py --generate-candidates
open ~/.timefinder_cache/calendar_review/calendar_candidates.md
python3 timefinder/timefinder.py --review-ics ~/.timefinder_cache/calendar_review/calendar_candidates.ics
```

Run tests:

```bash
pytest timefinder/tests/ -v
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `slack: command not found` | `~/.local/bin` not on PATH | Add to `~/.zshrc`, reload shell |
| `invalid_auth` from TimeFinder | Expired or wrong token | Run `slack auth token` again and update `slack_channels.json` |
| `Slack configuration not found` | Missing config file | Complete Step 3 |
| `Gmail configuration not found` | Missing `gmail_config.json` | Complete Step 4A or 4B |
| App passwords denied / unavailable | Workspace policy | Use OAuth — Step 4B |
| `Google token not found` | OAuth not run | Run `--setup-google-auth` (Step 4B.4) |
| Gmail API 403 / access blocked | OAuth app not allowed | Workspace admin must allow app; use Internal OAuth or test-user list |
| `Gmail config requires email and app_password` | Wrong auth mode | Use `"auth": "oauth"` for Workspace |
| `slack auth token` fails | CLI not logged in | Run `slack auth login` first |
| Token expired | Service tokens rotate | Repeat Step 2 and update `slack_channels.json` |
| Google sync fails | Missing OAuth token | Run `--setup-google-auth` |

---

## Security reminders

- Never commit `~/.timefinder_cache/slack_channels.json`, `gmail_config.json`, or tokens to git.
- Treat `xoxp-` tokens like passwords — they grant access to your Slack workspace.
- Raw message backups under `~/.timefinder_cache/` may contain sensitive content; keep that directory private.

---

[← Back to TimeFinder README](README.md)
