# vast-opstat Setup Guide

Step-by-step instructions for running **vast-opstat** on a client machine with no prior
Python experience. vast-opstat is a terminal dashboard that queries your VAST VMS for
live NFS or NVMe-oTCP performance statistics.

---

## What You Need

| Item | Details |
|------|---------|
| **Python** | Version 3.8 or newer |
| **Network** | HTTPS access to your VMS (default port 443) |
| **Credentials** | VMS username and password (typically `admin`) |
| **Git** | Optional but recommended for cloning the repository |

No third-party Python packages are required to run vast-opstat — it uses the standard
library only. See [requirements.txt](requirements.txt).

---

## 1. Install Python

### macOS

**Option A — Official installer (simplest)**

1. Download Python from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer and complete the wizard.
3. Open **Terminal** and verify:

```bash
python3 --version
```

You should see `Python 3.8` or higher.

**Option B — Homebrew**

```bash
brew install python
python3 --version
```

### Windows

1. Download Python from [python.org/downloads](https://www.python.org/downloads/).
2. Run the installer.
3. **Important:** Check **"Add python.exe to PATH"** at the bottom of the first screen.
4. Click **Install Now**.
5. Open **PowerShell** or **Command Prompt** and verify:

```powershell
python --version
```

You should see `Python 3.8` or higher.

---

## 2. Get the Code

If you already have the repository, skip to the next section.

```bash
git clone <your-repo-url> kmactools
cd kmactools/vast/vast-opstat
```

If you received a zip archive, extract it and open a terminal in the
`vast/vast-opstat` folder.

---

## 3. Create a Virtual Environment

A virtual environment keeps vast-opstat isolated from other Python projects on your
machine. Run these commands from the `vast/vast-opstat` directory.

### macOS / Linux

```bash
cd vast/vast-opstat
python3 -m venv .venv
source .venv/bin/activate
```

Your prompt should now show `(.venv)` at the beginning.

### Windows (PowerShell)

```powershell
cd vast\vast-opstat
python -m venv .venv
.venv\Scripts\Activate.ps1
```

If PowerShell blocks the script, run once (as Administrator):

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then activate again.

### Windows (Command Prompt)

```cmd
cd vast\vast-opstat
python -m venv .venv
.venv\Scripts\activate.bat
```

---

## 4. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

For vast-opstat runtime use, this step confirms your environment is ready. The
requirements file documents that no external packages are needed; `pip` will simply
finish with no packages installed.

---

## 5. Run vast-opstat

Make sure your virtual environment is **activated** (`(.venv)` visible in the prompt).

### NVMe-oTCP block monitoring (cluster-wide)

**macOS / Linux:**

```bash
./vast-opstat.py --block --nvme-over-tcp \
  --vms var203.selab.vastdata.com \
  --user admin --password YOUR_PASSWORD
```

**Windows:**

```powershell
python vast-opstat.py --block --nvme-over-tcp `
  --vms var203.selab.vastdata.com `
  --user admin --password YOUR_PASSWORD
```

Replace `var203.selab.vastdata.com` with your VMS hostname or IP. If you omit
`--password`, the tool prompts you securely.

### NVMe-oTCP with volume scoping

```bash
./vast-opstat.py --block --nvme-over-tcp \
  --vms var203.selab.vastdata.com \
  --volumes kmacs-block-vol1,kmacs-block-vol2 \
  --user admin
```

### NFS v3 monitoring

```bash
./vast-opstat.py --nfs --version=3.0 \
  --vms var203.selab.vastdata.com \
  --user admin
```

### Remote cluster via SSH tunnel (Teleport / zero-trust)

When the VMS is on a remote cluster behind Teleport, a bastion, or other zero-trust
access, open an SSH port forward first, then point opstat at the local end of the
tunnel:

```bash
# Terminal 1 — forward local port 8443 to remote VMS HTTPS (443)
ssh -L 8443:var203.selab.vastdata.com:443 user@jump-host

# Terminal 2 — connect through the tunnel
./vast-opstat.py --nfs --version=3.0 \
  --vms localhost --vms-port 8443 --user admin
```

Use the same `--vms localhost --vms-port <LOCAL_PORT>` pattern for NVMe-oTCP block
monitoring. Default port is `443` when `--vms-port` is omitted.

### Discover available metrics (no live dashboard)

```bash
./vast-opstat.py --block --nvme-over-tcp \
  --vms var203.selab.vastdata.com --discover-metrics
```

### Debug API calls

```bash
./vast-opstat.py --block --nvme-over-tcp \
  --vms var203.selab.vastdata.com --log-api-calls --discover-metrics
```

Log file location is printed on startup under `/tmp/vast-opstat-api-*.log`.

---

## 6. Using the Dashboard

Once running, the terminal shows live statistics. Key controls for NVMe-oTCP:

| Key | Action |
|-----|--------|
| `h` | Host / initiator drill-down |
| `v` | VIP path drill-down |
| `c` | cNode path drill-down |
| `p` | Return to main view |
| `r` | Reset session stats |
| `q` | Quit |

Full NVMe-oTCP documentation: [NVMe_TCP_README.md](NVMe_TCP_README.md)

---

## 7. Running Tests (Optional)

From the **repository root** (not only `vast-opstat`):

```bash
pip install pytest pytest-mock
pytest tests/test_vast_opstat.py -v
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `python3: command not found` (Mac/Linux) | Install Python or use `python` instead of `python3` |
| `python: command not found` (Windows) | Re-run installer with **Add to PATH** checked |
| `Permission denied` running `./vast-opstat.py` | Run `python vast-opstat.py ...` instead |
| SSL / certificate warnings | Expected in lab environments; opstat disables cert verification for internal VMS |
| Blank or warming-up stats | Wait one refresh cycle (~5 s) for counter delta baselines |
| Volume not found | Verify name with `GET /api/volumes/` or `--discover-metrics` |

---

## Next Steps

- [README.md](README.md) — protocol matrix and shared CLI options
- [NVMe_TCP_README.md](NVMe_TCP_README.md) — block monitoring deep dive
- [NFSv3_README.md](NFSv3_README.md) — NFS v3 monitoring reference
