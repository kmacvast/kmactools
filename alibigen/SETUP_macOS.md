# AlibiGen macOS Environment Setup

> **Platform:** AlibiGen is developed and tested on **macOS only**.
> It could be ported to Windows if someone wants to do that work — this author has no Windows workstations for development. macOS > Windows.

Complete this guide before running any AlibiGen scripts. When finished, return to [README.md](README.md) for day-to-day usage.

---

## Step 1 — Install and configure the Slack CLI

AlibiGen uses the **[Slack CLI](https://docs.slack.dev/tools/slack-cli/)** — an open-source command-line tool from Slack for creating, managing, and interacting with Slack apps and workspace APIs from your terminal.

We did not build the Slack CLI. Credit and thanks to the Slack developer platform team for maintaining it. Install and authenticate it as described below; AlibiGen then uses it for setup tasks like generating a service token and verifying API access.

The Slack CLI is used to authenticate, generate a service token for AlibiGen, resolve channel IDs, and verify API access.

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

Try a few more commands to get comfortable with the tool:

```bash
# Browse available commands and flags
slack help

# List workspaces you are logged into
slack auth list

# Call Slack Web API methods directly from the terminal
slack api conversations.list
slack api users.list

# Inspect a specific channel (replace CHANNEL_ID with a real ID)
slack api conversations.info --query channel=CHANNEL_ID
```

See the [Slack CLI documentation](https://docs.slack.dev/tools/slack-cli/) for guides, command reference, and troubleshooting.

---

## Step 2 — Generate a Slack service token (for AlibiGen)

AlibiGen needs a **user service token** to read channel history. The easiest way to get one is through the Slack CLI — no browser dev tools required.

# Guide: Extracting Slack Browser Credentials for Thread Harvesting

This guide provides step-by-step instructions for extracting high-privilege Slack session credentials (`xoxc` tokens and `xoxd` cookies) from your web browser to use with `threadharvest.py`.

## Prerequisites
* A desktop web browser (Google Chrome, Microsoft Edge, Mozilla Firefox, or Apple Safari).
* Logged into your target Slack workspace via the web app (`https://app.slack.com/client/...`).

---

## Step-by-Step Instructions

### Step 1: Open Developer Tools
1. Navigate to your Slack workspace in your browser.
2. Open the browser's Developer Tools panel:
   * **Mac:** Press `Cmd + Option + I`
   * **Windows / Linux:** Press `F12` or `Ctrl + Shift + I`

### Step 2: Configure the Network Tab
1. Look at the top menu bar of the Developer Tools panel and click on the **Network** tab.
2. Find the **Filter** box (usually in the upper-left corner of the Network pane).
3. Type `client.counts` into the Filter box to isolate the exact API traffic needed.

### Step 3: Trigger Slack API Activity
1. Go back to your active Slack window on the left side of the screen.
2. Click on a different channel or direct message in your sidebar.
3. You will see a new request named `client.counts?...` appear in the Network list box. Click on it once to open its details pane.

### Step 4: Extract the `xoxd` Session Cookie
1. In the right-hand details pane that opened for `client.counts`, click on the **Cookies** sub-tab (located on the horizontal bar with Headers, Payload, Preview, etc.).
2. Look at the table of Request Cookies. Find the row under the **Name** column labeled **`d`**.
3. Double-click or select the entire corresponding value in the **Value** column. It will be a long string starting with **`xoxd-`** and will contain URL-encoded characters (like `%2F` or `%2B`).
4. Copy this string entirely.

### Step 5: Extract the `xoxc` Auth Token
1. Switch from the Cookies sub-tab to the **Payload** sub-tab (or **Form Data** under Headers depending on your browser version).
2. Look down the list of parameter keys until you find the row explicitly named **`token`**.
3. Copy the entire value next to it. This string will start with **`xoxc-`** and is a clean alphanumeric string.

---

## Step 6: Update Your Credentials Configuration

Open your local credentials file (`~/.slack/credentials.json`) and update it with the following JSON layout, ensuring you paste your extracted values cleanly:

```json
{
  "YOUR_TEAM_ID_HERE": {
    "token": "PASTE_YOUR_xoxc-_TOKEN_HERE",
    "refresh_token": "PASTE_YOUR_xoxd-_COOKIE_HERE",
    "team_domain": "vastdata",
    "team_id": "YOUR_TEAM_ID_HERE",
    "user_id": "YOUR_USER_ID_HERE"
  }
}
```

Keep the token private. Never commit it to git.

---

## Step 3 — Save credentials for AlibiGen

AlibiGen stores automation credentials in:

**`~/.alibigen_cache/slack_channels.json`**

### Option A — Interactive setup (recommended)

Run the channel resolver; it prompts for your token:

```bash
cd ~/path/to/kmactools
python3 alibigen/resolve_alibigen_channels.py
```

When prompted:

- **Token** → paste the `xoxp-...` service token from Step 2
- **d cookie** → press Enter to skip (not needed for `xoxp-` tokens)

Resolve the channels, DMs, or group DMs you want to track, then save when prompted.

Or use the one-shot initializer (fixed channel list in the script):

```bash
python3 alibigen/init_alibigen_channels.py
```

When prompted, paste the `xoxp-...` service token. Skip the d cookie if asked.

### Option B — Manual config file

Create the cache directory and config file:

```bash
mkdir -p ~/.alibigen_cache
```

Create `~/.alibigen_cache/slack_channels.json`:

```json
{
  "slack_token": "xoxp-your-service-token-here",
  "slack_d_cookie": "",
  "channels": {}
}
```

Then run `resolve_alibigen_channels.py` to populate the `channels` map, or add channel name → ID pairs manually.

---

## Step 4 — Python environment (macOS)

From the repo root:

```bash
cd ~/path/to/kmactools
python3 -m venv .venv
source .venv/bin/activate
pip install pytest   # for running tests
```

---

## Step 5 — Verify AlibiGen end-to-end

```bash
source ~/path/to/kmactools/.venv/bin/activate
cd ~/path/to/kmactools

# Gather Slack messages (Gmail skipped if not configured)
python3 alibigen/get_alibigen_messages.py --slack

# Generate calendar candidates
python3 alibigen/get_alibigen_candidates.py

# Review output
open ~/.alibigen_cache/calendar_review/calendar_candidates.md
```

Run tests:

```bash
pytest alibigen/tests/ -v
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `slack: command not found` | `~/.local/bin` not on PATH | Add to `~/.zshrc`, reload shell |
| `invalid_auth` from AlibiGen | Expired or wrong token | Run `slack auth token` again and update `slack_channels.json` |
| `Slack configuration not found` | Missing config file | Complete Step 3 |
| `slack auth token` fails | CLI not logged in | Run `slack auth login` first |
| Token expired | Service tokens rotate | Repeat Step 2 and update `slack_channels.json` |

---

## Security reminders

- Never commit `~/.alibigen_cache/slack_channels.json` or tokens to git.
- Treat `xoxp-` tokens like passwords — they grant access to your Slack workspace.
- Raw message backups under `~/.alibigen_cache/` may contain sensitive content; keep that directory private.

---

[← Back to AlibiGen README](README.md)
