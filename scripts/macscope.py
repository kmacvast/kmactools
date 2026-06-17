#!/usr/bin/env python3
################################################################################
# Script: macscope.py
# Descr : macOS network, VPN, firewall, endpoint, and SMB diagnostic snapshot
# Date  : 2026-06-17
# Author: KMac
# Usage : ./macscope.py
################################################################################

import datetime
import functools
import os
import platform
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

BLUE = "\033[1;34m"
GREEN = "\033[1;32m"
YELLOW = "\033[1;33m"
RED = "\033[1;31m"
BOLD = "\033[1m"
NC = "\033[0m"

SCRIPT_START_TIME = time.time()
HOST_SHORT = socket.gethostname().split(".")[0] or "mac"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUTFILE = Path.home() / "Downloads" / f"macscope_{HOST_SHORT}_{STAMP}.log"
STEP_COUNT = 0
STEP_TOTAL = 25  # one per collect_* call in main()
LOG_FH = None

SENSITIVE_WORDS = re.compile(
    r"password|passwd|secret|token|apikey|api_key|credential", re.IGNORECASE
)
_REDACT_RE = re.compile(
    r"(?i)(password|passwd|secret|token|apikey|api_key|credential)(\s*[=:]\s*)\S+"
)
SMB_WORDS = re.compile(
    r"smb|cifs|netbios|netbt|dfs|oplock|lease|signing|kerberos|gss|ntlm|negotiate",
    re.IGNORECASE,
)
SECURITY_WORDS = re.compile(
    r"vpn|tunnel|packet|filter|proxy|dns|networkextension|endpoint|security|firewall|edr|mdm|"
    r"cato|tailscale|zscaler|globalprotect|anyconnect|forticlient|sentinel|crowdstrike|jamf|"
    r"defender|carbonblack|netskope|paloalto|palo alto|checkpoint|wireguard|openvpn|sonicwall",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def ctext(text, color):
    return f"{color}{text}{NC}" if sys.stdout.isatty() else text


def screen(text="", color=None, end="\n", flush=True):
    print(ctext(text, color) if color else text, end=end, flush=flush)


def log(text=""):
    if LOG_FH:
        LOG_FH.write(text + "\n")
        LOG_FH.flush()


def log_block(text=""):
    for line in str(text).splitlines():
        log(line)


def banner():
    screen()
    screen("=== Macscope diagnostic data collection ===", BOLD + BLUE)
    screen(f"Diagnostic tasks: {STEP_TOTAL}", BLUE)
    screen()
    screen("Full command output is saved in the log file.")
    screen(f"Log file: {OUTFILE}", GREEN)
    screen()


def section(title):
    log()
    log(f"=== {title} ===")


def subheader(title):
    log()
    log(f"--- {title} ---")


def elapsed():
    total = int(time.time() - SCRIPT_START_TIME)
    return f"{total // 60:02d}:{total % 60:02d}"


def status(title):
    global STEP_COUNT
    STEP_COUNT += 1
    task = ctext(f"[Task {STEP_COUNT:>2}/{STEP_TOTAL}]", BLUE + BOLD)
    timer = ctext(f"[{elapsed()}]", YELLOW + BOLD)
    screen(f"{task} {timer} {title}")


def say(text):
    screen(f"    • {text}")


def ok(text="done"):
    screen(f"      ✓ {text}", GREEN)


def note(text):
    screen(f"      {text}", YELLOW)


def fail_screen(text):
    screen(f"      ✗ {text}", RED)


# ---------------------------------------------------------------------------
# Command execution helpers
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def have(cmd):
    return shutil.which(cmd) is not None


def redact_line(line):
    if SENSITIVE_WORDS.search(line):
        return _REDACT_RE.sub(r"\1\2<redacted>", line)
    return line


def redact_text(text):
    return "\n".join(redact_line(line) for line in text.splitlines())


def _merge_output(stdout, stderr):
    sep = "\n" if stdout and stderr else ""
    return redact_text(((stdout or "") + sep + (stderr or "")).rstrip("\n"))


def command_label(cmd, sudo=False):
    shown = " ".join(cmd)
    return f"sudo -n {shown}" if sudo else shown


def run(cmd, sudo=False, timeout=30, long=False, message=None):
    if message:
        screen(f"    • {message}", end="")
    command = cmd[:]
    shown = command_label(command, sudo=sudo)
    if sudo:
        command = ["sudo", "-n"] + command
    log()
    log(f"$ {shown}")
    try:
        proc = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
    except FileNotFoundError:
        log(f"Command not found: {cmd[0]}")
        return ""
    start = time.time()
    last_dot = start
    dots_started = False
    while proc.poll() is None:
        now = time.time()
        if now - start > timeout:
            proc.kill()
            try:
                stdout, stderr = proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
            output = _merge_output(stdout, stderr)
            if output:
                log_block(output)
            log(f"Command timed out after {timeout}s: {shown}")
            if message or dots_started:
                screen(f" {ctext('timed out', YELLOW)}")
            else:
                note(f"timed out after {timeout}s")
            return output
        if long and now - last_dot >= 3:
            if not message and not dots_started:
                screen("    • Still working", end="")
            screen(".", end="")
            dots_started = True
            last_dot = now
        time.sleep(0.2)
    stdout, stderr = proc.communicate()
    if message:
        screen(f" {ctext('done', GREEN)}")
    elif dots_started:
        screen()
    output = _merge_output(stdout, stderr)
    if output:
        log_block(output)
    if proc.returncode != 0:
        log(f"Command exited with rc={proc.returncode}")
    return output


def shell(cmd, sudo=False, timeout=30, long=False, message=None):
    return run(["/bin/sh", "-c", cmd], sudo=sudo, timeout=timeout, long=long, message=message)


def clean_lines(text):
    return [line.strip() for line in text.splitlines() if line.strip()]


def read_file(path):
    p = Path(path).expanduser()
    log()
    log(f"$ cat {p}")
    try:
        if not p.exists():
            log(f"Not found: {p}")
            return ""
        if not p.is_file():
            log(f"Not a regular file: {p}")
            return ""
        data = redact_text(p.read_text(errors="replace").rstrip("\n"))
        if data:
            log_block(data)
        else:
            log(f"File is empty: {p}")
        return data
    except PermissionError:
        log(f"Permission denied: {p}")
        return ""
    except OSError as err:
        log(f"Unable to read {p}: {err}")
        return ""


# ---------------------------------------------------------------------------
# Network inventory helpers
# ---------------------------------------------------------------------------

def network_services():
    output = run(["networksetup", "-listallnetworkservices"], timeout=20)
    services = []
    for line in clean_lines(output):
        if line.startswith("An asterisk"):
            continue
        services.append(line.lstrip("*"))
    return services


def interface_names():
    output = run(["ifconfig", "-l"], timeout=10)
    return [item for item in output.split() if item]


def tunnel_interfaces(interfaces):
    pattern = re.compile(r"^(utun|tun|tap|ppp|ipsec|wg|llw|awdl|bridge)\d*$", re.IGNORECASE)
    return [name for name in interfaces if pattern.search(name)]


def list_network_processes():
    output = run(["ps", "axww", "-o", "pid=,user=,comm=,args="], timeout=20)
    return [
        line for line in output.splitlines()
        if SECURITY_WORDS.search(line) and "macscope.py" not in line
    ]


def log_rows(title, rows, empty_message):
    section(title)
    if rows:
        for row in rows:
            log(row)
    else:
        log(empty_message)


# ---------------------------------------------------------------------------
# Application firewall helpers
# ---------------------------------------------------------------------------

def extract_app_paths(text):
    paths = []
    for line in text.splitlines():
        candidates = re.findall(
            r"/(?:Applications|System|Library|Users)/[^\n]+?"
            r"(?:\.app|\.appex|\.xpc|\.bundle|\.plugin|\.framework|\.dylib|\.systemextension|\.networkextension)",
            line,
        )
        for candidate in candidates:
            cleaned = candidate.strip().rstrip(" ,;:)")
            if cleaned not in paths:
                paths.append(cleaned)
    return paths


def app_bundle_root(path):
    p = Path(path)
    parts = p.parts
    for idx, part in enumerate(parts):
        if part.endswith(
            (".app", ".appex", ".xpc", ".bundle", ".plugin", ".systemextension", ".networkextension")
        ):
            return Path(*parts[: idx + 1])
    return p


def read_info_plist(bundle):
    info = bundle / "Contents" / "Info.plist"
    if not info.exists():
        return {}
    try:
        with info.open("rb") as fh:
            data = plistlib.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def app_metadata(paths):
    section("Application Firewall App Metadata")
    if not paths:
        log("No application paths were parsed from socketfilterfw output.")
        return
    for path in paths:
        bundle = app_bundle_root(path)
        subheader(str(bundle))
        info = read_info_plist(bundle)
        bundle_id = info.get("CFBundleIdentifier", "")
        version = info.get("CFBundleShortVersionString", "") or info.get("CFBundleVersion", "")
        executable = info.get("CFBundleExecutable", "")
        if SMB_WORDS.search(str(bundle)) or SMB_WORDS.search(bundle_id):
            category = "SMB-related"
        elif SECURITY_WORDS.search(str(bundle)) or SECURITY_WORDS.search(bundle_id):
            category = "Security/VPN/filter-related"
        else:
            category = "General"
        log(f"Category: {category}")
        log(f"Bundle ID: {bundle_id or 'Unknown'}")
        log(f"Version: {version or 'Unknown'}")
        log(f"Executable: {executable or 'Unknown'}")
        log(f"Exists: {'yes' if bundle.exists() else 'no'}")
        if category != "General":
            shell(
                f"codesign -dv --verbose=4 '{bundle}' 2>&1 | egrep "
                f"'Identifier=|TeamIdentifier=|Authority=|Runtime Version=|Sealed Resources|designated' || true",
                timeout=20,
            )
            shell(
                f"mdls -name kMDItemCFBundleIdentifier -name kMDItemVersion "
                f"-name kMDItemDisplayName -name kMDItemContentCreationDate "
                f"-name kMDItemFSName '{bundle}' 2>/dev/null || true",
                timeout=15,
            )


# ---------------------------------------------------------------------------
# Collection tasks (in call order)
# ---------------------------------------------------------------------------

def collect_run_context():
    status("Gathering basic Mac and OS identity")
    say("Recording hostname, current user, macOS version, and kernel details.")
    section("Run Context")
    run(["date", "+%Y-%m-%d %H:%M:%S %Z"], timeout=10)
    run(["hostname"], timeout=10)
    run(["whoami"], timeout=10)
    run(["sw_vers"], timeout=10)
    run(["uname", "-a"], timeout=10)
    shell(
        "scutil --get ComputerName 2>/dev/null; "
        "scutil --get LocalHostName 2>/dev/null; "
        "scutil --get HostName 2>/dev/null",
        timeout=10,
    )
    ok()


def collect_network_overview():
    status("Mapping active network services, interfaces, and VPN tunnels")
    say("Listing configured network services and hardware ports.")
    section("Network Services")
    services = network_services()
    run(["networksetup", "-listnetworkserviceorder"], timeout=20)
    run(["networksetup", "-listallhardwareports"], timeout=20)
    section("Interfaces")
    interfaces = interface_names()
    run(["ifconfig"], timeout=30)
    tunnels = tunnel_interfaces(interfaces)
    log_rows("Tunnel and VPN-Like Interfaces", tunnels, "No tunnel or VPN-like interfaces detected.")
    for name in tunnels:
        subheader(name)
        run(["ifconfig", name], timeout=10)
    log_rows(
        "VPN, Filter, Proxy, and Endpoint Processes",
        list_network_processes(),
        "No obvious VPN, filter, proxy, or endpoint processes detected.",
    )
    ok(f"found {len(services)} network services and {len(tunnels)} tunnel/VPN-like interfaces")
    return services, tunnels


def collect_system_extensions_and_profiles():
    status("Looking for Network Extensions, VPN profiles, and device-management controls")
    say("Looking for packet tunnels, content filters, DNS proxies, and other system extensions.")
    section("System Extensions")
    if have("systemextensionsctl"):
        run(["systemextensionsctl", "list"], timeout=30)
    else:
        log("systemextensionsctl not found.")
    section("Network Configuration Profiles")
    shell(
        "profiles list 2>/dev/null | egrep -i "
        "'vpn|dns|proxy|filter|network|content|security|extension|mdm|smb' || true",
        timeout=30,
    )
    shell("scutil --nc list 2>/dev/null || true", timeout=20)
    ok()


def collect_dns_and_proxy(services):
    status("Reading DNS and proxy settings")
    say("Capturing resolver order, DNS servers, search domains, and per-service DNS settings.")
    section("DNS Configuration")
    run(["scutil", "--dns"], timeout=30)
    shell("cat /etc/resolv.conf 2>/dev/null || true", timeout=10)
    if services:
        subheader("DNS Servers by Network Service")
        for service in services:
            log()
            log(f"[{service}]")
            run(["networksetup", "-getdnsservers", service], timeout=15)
    section("Proxy Configuration")
    if not services:
        log("No network services found.")
        ok()
        return
    for service in services:
        subheader(service)
        run(["networksetup", "-getwebproxy", service], timeout=15)
        run(["networksetup", "-getsecurewebproxy", service], timeout=15)
        run(["networksetup", "-getsocksfirewallproxy", service], timeout=15)
        run(["networksetup", "-getautoproxyurl", service], timeout=15)
        run(["networksetup", "-getproxybypassdomains", service], timeout=15)
    ok()


def collect_smb_config_files():
    status("Reading SMB client configuration files")
    say("Checking system and user nsmb.conf locations plus automounter files that can affect SMB mounts.")
    section("SMB Configuration Files")
    candidates = [
        "/etc/nsmb.conf",
        str(Path.home() / "Library" / "Preferences" / "nsmb.conf"),
        "/Library/Preferences/nsmb.conf",
        "/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist",
        "/Library/Preferences/SystemConfiguration/com.apple.smb.server",
        "/etc/auto_master",
        "/etc/auto_smb",
        "/etc/auto_home",
        "/etc/fstab",
    ]
    for path in candidates:
        subheader(path)
        read_file(path)
    ok()


def collect_smb_mounts_and_shares():
    status("Inspecting mounted SMB shares and negotiated session details")
    say("Asking macOS what SMB shares are mounted and what options were negotiated.")
    section("SMB Mounts and Share Details")
    shell("mount | egrep -i 'smb|cifs|//|/Volumes' || true", timeout=15)
    shell("df -h | egrep -i 'smb|cifs|//|/Volumes' || true", timeout=15)
    shell("smbutil statshares -a 2>&1 || true", timeout=30)
    shell("smbutil statshares -m 2>&1 || true", timeout=30)
    shell("smbutil multichannel -a 2>&1 || true", timeout=30)
    shell("smbutil status 2>&1 || true", timeout=20)
    shell("smbutil view 2>&1 || true", timeout=20)
    ok()


def collect_smb_processes_and_files():
    status("Checking SMB processes, open files, and SMB-related sockets")
    say("Looking for active SMB helpers, open SMB files, and port 445/139 activity.")
    section("SMB Processes, Files, and Sockets")
    shell(
        "ps axww -o pid,user,comm,args | egrep -i 'smb|netbios|netbiosd|NetAuth|mount_smbfs|smbd|nmbd' "
        "| egrep -v 'egrep|macscope.py' || true",
        timeout=20,
    )
    if have("lsof"):
        shell(
            "lsof -nP | egrep -i 'smb|nsmb|smbfs|mount_smbfs|netbios|NetAuth' | head -n 300 || true",
            sudo=True, timeout=45, long=True, message="Scanning open files for SMB-related activity",
        )
        shell(
            "lsof -nP -iTCP:445 -iTCP:139 -iUDP:137 -iUDP:138 2>/dev/null || true",
            sudo=True, timeout=30, long=True, message="Checking SMB and NetBIOS socket ownership",
        )
    shell("launchctl print system 2>/dev/null | egrep -i 'smb|netbios|NetAuth' || true", timeout=30)
    shell("launchctl print gui/$(id -u) 2>/dev/null | egrep -i 'smb|netbios|NetAuth' || true", timeout=30)
    ok()


def collect_smb_system_settings():
    status("Reading SMB-related system settings")
    say("Reading SMB-related kernel and preference settings where available.")
    section("SMB System Settings")
    shell("sysctl -a 2>/dev/null | egrep -i '(^net\\.smb|smbfs|smb)' || true", timeout=30)
    shell("kextstat 2>/dev/null | egrep -i 'smb|smbfs' || true", timeout=15)
    shell("kmutil showloaded 2>/dev/null | egrep -i 'smb|smbfs' || true", timeout=30)
    shell(
        "defaults read /Library/Preferences/SystemConfiguration/com.apple.smb.server 2>/dev/null || true",
        timeout=15,
    )
    shell("defaults read /Library/Preferences/com.apple.NetworkBrowser 2>/dev/null || true", timeout=15)
    shell("sharing -l 2>/dev/null | egrep -i 'smb|file sharing|windows' -A5 -B2 || true", timeout=20)
    ok()


def collect_smb_directory_snapshot():
    status("Taking a lightweight snapshot of SMB-related directories")
    say("Listing /Volumes and SMB-related preference directories without walking the whole filesystem.")
    section("SMB Related Directories")
    shell("ls -la /Volumes 2>/dev/null || true", timeout=15)
    shell(
        "find /Volumes -maxdepth 2 -type d 2>/dev/null | head -n 200 || true",
        timeout=30, long=True, message="Walking the top of /Volumes for mounted shares",
    )
    shell("ls -la /var/db/samba 2>/dev/null || true", sudo=True, timeout=15)
    shell(
        "ls -la /Library/Preferences/SystemConfiguration | egrep -i 'smb|netbios|network' || true",
        timeout=15,
    )
    ok()


def collect_smb_recent_logs():
    status("Searching recent macOS logs for SMB client events")
    say("Querying unified logs for recent SMB, Kerberos, NTLM, lease, oplock, and smbfs messages.")
    section("Recent SMB Logs")
    predicate = (
        "process CONTAINS[c] 'smb' OR "
        "process CONTAINS[c] 'netbios' OR "
        "process CONTAINS[c] 'NetAuth' OR "
        "subsystem CONTAINS[c] 'smb' OR "
        "eventMessage CONTAINS[c] 'smb' OR "
        "eventMessage CONTAINS[c] 'smbfs' OR "
        "eventMessage CONTAINS[c] 'mount_smbfs' OR "
        "eventMessage CONTAINS[c] 'netbios' OR "
        "eventMessage CONTAINS[c] 'ntlm' OR "
        "eventMessage CONTAINS[c] 'kerberos' OR "
        "eventMessage CONTAINS[c] 'gss' OR "
        "eventMessage CONTAINS[c] 'oplock' OR "
        "eventMessage CONTAINS[c] 'lease'"
    )
    shell(
        f"log show --last 4h --style compact --predicate \"{predicate}\" 2>/dev/null | tail -n 500 || true",
        timeout=120, long=True,
    )
    ok()


def collect_smb_client_caches():
    status("Inspecting SMB client cache and preference state")
    say("Looking for SMB, Network Browser, Finder, and per-user cache/preferences that can affect NAS behavior.")
    section("SMB Client Caches and Preferences")
    paths = [
        "~/Library/Preferences/nsmb.conf",
        "~/Library/Preferences/com.apple.NetworkBrowser.plist",
        "~/Library/Preferences/com.apple.finder.plist",
        "~/Library/Caches",
        "/Library/Preferences/nsmb.conf",
        "/Library/Preferences/SystemConfiguration/com.apple.smb.server.plist",
        "/Library/Preferences/SystemConfiguration",
    ]
    for path in paths:
        subheader(path)
        shell(
            f"ls -la {path} 2>/dev/null | egrep -i 'smb|cifs|networkbrowser|finder|netauth|dfs|nsmb' || true",
            timeout=20,
        )
    ok()


def collect_open_smb_volume_handles():
    status("Checking open files on mounted SMB volumes")
    say("Looking for Finder, creative apps, sync tools, or background services holding files open on network volumes.")
    section("Open Files on SMB and Network Volumes")
    shell("mount | egrep -i 'smb|cifs|/Volumes' || true", timeout=15)
    if have("lsof"):
        shell(
            "lsof -nP | egrep '/Volumes|smbfs|mount_smbfs|NetAuth|netbios' | head -n 500 || true",
            sudo=True, timeout=60, long=True, message="Scanning open files on mounted volumes",
        )
    else:
        log("lsof not found.")
    ok()


def collect_spotlight_state():
    status("Checking Spotlight indexing state")
    say("Checking whether Spotlight is indexing network volumes or generating metadata traffic.")
    section("Spotlight State")
    shell("mdutil -sa 2>&1 || true", timeout=30)
    shell(
        'for v in /Volumes/*; do [ -d "$v" ] && echo "### $v" && mdutil -s "$v" 2>&1; done',
        timeout=45, long=True, message="Checking Spotlight state on mounted volumes",
    )
    shell(
        "ps axww -o pid,user,comm,args | egrep -i 'mds|mdworker|mdworker_shared|mdimport|spotlight' "
        "| egrep -v 'egrep|macscope.py' || true",
        timeout=20,
    )
    ok()


def collect_fsevents_state():
    status("Checking filesystem event services")
    say("Looking for FSEvents activity that can affect creative apps and network-volume change detection.")
    section("FSEvents State")
    shell(
        "ps axww -o pid,user,comm,args | egrep -i 'fseventsd|fsevents' | egrep -v 'egrep|macscope.py' || true",
        timeout=20,
    )
    shell(
        "lsof -nP | egrep -i 'fseventsd|/.fseventsd|/Volumes/.*/.fseventsd' | head -n 300 || true",
        sudo=True, timeout=45, long=True, message="Checking FSEvents open files",
    )
    shell("find /Volumes -maxdepth 2 -name .fseventsd -print 2>/dev/null | head -n 100 || true", timeout=30)
    ok()


def collect_plugin_inventory():
    status("Expanding plugin and Network Extension inventory")
    say("Looking for packet tunnels, content filters, DNS proxies, transparent proxies, and app plugins.")
    section("Plugin and Network Extension Inventory")
    if have("pluginkit"):
        shell(
            "pluginkit -m -A 2>/dev/null | egrep -i "
            "'network|vpn|packet|filter|dns|proxy|tunnel|content|security|smb|fileprovider|finder' || true",
            timeout=60, long=True,
        )
    else:
        log("pluginkit not found.")
    shell("systemextensionsctl list 2>/dev/null || true", timeout=30)
    shell(
        "profiles list 2>/dev/null | egrep -i "
        "'network|vpn|packet|filter|dns|proxy|tunnel|content|security|smb|fileprovider|privacy|tcc' || true",
        timeout=45, long=True,
    )
    ok()


def collect_tcc_state():
    status("Checking macOS privacy controls and recent denials")
    say("Looking for privacy or filesystem-access denials that can masquerade as SMB failures.")
    section("TCC Privacy and Access Control State")
    shell(
        "log show --last 4h --style compact --predicate "
        "\"subsystem CONTAINS[c] 'TCC' OR eventMessage CONTAINS[c] 'deny' OR "
        "eventMessage CONTAINS[c] 'privacy' OR eventMessage CONTAINS[c] 'Network Volumes' OR "
        "eventMessage CONTAINS[c] 'Removable Volumes'\" 2>/dev/null | tail -n 300 || true",
        timeout=90, long=True,
    )
    shell("ls -la ~/Library/Application\\ Support/com.apple.TCC 2>/dev/null || true", timeout=15)
    shell(
        "ls -la /Library/Application\\ Support/com.apple.TCC 2>/dev/null || true",
        sudo=True, timeout=15,
    )
    ok()


def collect_deep_smb_edge_logs():
    status("Searching deeper SMB edge-case logs")
    say("Looking for file handle, lease, oplock, durable-handle, reconnect, compound request, and metadata errors.")
    section("Deep SMB Edge-Case Logs")
    predicate = (
        "eventMessage CONTAINS[c] 'smb_fid' OR "
        "eventMessage CONTAINS[c] 'fid' OR "
        "eventMessage CONTAINS[c] 'handle' OR "
        "eventMessage CONTAINS[c] 'lease' OR "
        "eventMessage CONTAINS[c] 'oplock' OR "
        "eventMessage CONTAINS[c] 'durable' OR "
        "eventMessage CONTAINS[c] 'compound' OR "
        "eventMessage CONTAINS[c] 'reconnect' OR "
        "eventMessage CONTAINS[c] 'multichannel' OR "
        "eventMessage CONTAINS[c] 'query_info' OR "
        "eventMessage CONTAINS[c] 'xattr' OR "
        "eventMessage CONTAINS[c] 'EINVAL' OR "
        "eventMessage CONTAINS[c] 'Invalid argument' OR "
        "eventMessage CONTAINS[c] 'smbfs'"
    )
    shell(
        f"log show --last 6h --style compact --predicate \"{predicate}\" 2>/dev/null | tail -n 700 || true",
        timeout=150, long=True,
    )
    ok()


def collect_smb_negotiation_summary():
    status("Building SMB negotiation summary")
    say("Summarizing negotiated SMB dialect, signing, encryption, multichannel, DFS, leasing, and session options.")
    section("SMB Negotiation Summary")
    output = shell("smbutil statshares -a 2>&1 || true", timeout=30)
    interesting = [
        line for line in output.splitlines()
        if re.search(
            r"SMB_VERSION|SIGNING|ENCRYPTION|MULTI|DFS|LEASE|SESSION|NEGOTIATE|SERVER|SHARE|USER|AUTH|DIALECT",
            line, re.IGNORECASE,
        )
    ]
    if interesting:
        subheader("Parsed SMB Negotiation Highlights")
        for line in interesting:
            log(line)
    else:
        log("No SMB negotiation highlights parsed from smbutil statshares output.")
    shell("smbutil multichannel -a 2>&1 || true", timeout=30)
    ok()


def collect_acl_permission_snapshots():
    status("Collecting ACL and permission snapshots")
    say("Checking permissions, ACLs, ownership, and extended attributes on mounted network volumes.")
    section("ACL, Permission, and Extended Attribute Snapshots")
    shell('for v in /Volumes/*; do [ -d "$v" ] && echo "### $v" && ls -lde "$v" 2>&1; done', timeout=30)
    shell(
        'for v in /Volumes/*; do [ -d "$v" ] && echo "### $v" && ls -le "$v" 2>&1 | head -n 80; done',
        timeout=45, long=True,
    )
    shell(
        'for v in /Volumes/*; do [ -d "$v" ] && echo "### $v" && xattr -l "$v" 2>&1 | head -n 80; done',
        timeout=45, long=True,
    )
    ok()


def collect_finder_network_preferences():
    status("Reading Finder and network browsing preferences")
    say("Checking Finder, Network Browser, DS_Store, and network-volume browsing preferences.")
    section("Finder and Network Browsing Preferences")
    shell("defaults read com.apple.finder 2>/dev/null || true", timeout=20)
    shell("defaults read com.apple.NetworkBrowser 2>/dev/null || true", timeout=20)
    shell("defaults read /Library/Preferences/com.apple.NetworkBrowser 2>/dev/null || true", timeout=20)
    shell("defaults read com.apple.desktopservices 2>/dev/null || true", timeout=20)
    shell("defaults read /Library/Preferences/com.apple.desktopservices 2>/dev/null || true", timeout=20)
    ok()


def collect_application_firewall():
    status("Reviewing Application Firewall entries and related app metadata")
    path = "/usr/libexec/ApplicationFirewall/socketfilterfw"
    say("Reading macOS Application Firewall settings and identifying apps that may touch network traffic.")
    section("Application Firewall")
    if not Path(path).exists():
        log("socketfilterfw not found.")
        note("socketfilterfw not found")
        return []
    run([path, "--getglobalstate"], timeout=15)
    run([path, "--getblockall"], timeout=15)
    run([path, "--getallowsigned"], timeout=15)
    run([path, "--getloggingmode"], timeout=15)
    run([path, "--getstealthmode"], timeout=15)
    output = run([path, "--listapps"], timeout=30)
    paths = extract_app_paths(output)
    app_metadata(paths)
    ok(f"parsed {len(paths)} application paths")
    return paths


def collect_pf_snapshot():
    status("Capturing PF firewall state without dumping it to the terminal")
    say("Saving PF state, rules, NAT, and non-Apple anchors to the log only.")
    section("PF Firewall")
    if not have("pfctl"):
        log("pfctl not found.")
        note("pfctl not found")
        return
    shell("pfctl -s info", sudo=True, timeout=15)
    shell("pfctl -s rules", sudo=True, timeout=15)
    shell("pfctl -s nat", sudo=True, timeout=15)
    anchors = shell(
        "pfctl -s Anchors 2>/dev/null | awk '{print $1}' | egrep -v '^$|^com\\.apple' | sort -u",
        sudo=True, timeout=15,
    )
    anchor_lines = clean_lines(anchors)
    if anchor_lines:
        subheader("Non-Apple PF Anchors")
        for anchor in anchor_lines:
            log(anchor)
        for anchor in anchor_lines:
            subheader(f"PF anchor {anchor} rules")
            shell(f"pfctl -a '{anchor}' -s rules", sudo=True, timeout=15)
    else:
        log("No non-Apple PF anchors found, unavailable, or sudo permission was not available.")
    ok()


def collect_socket_state():
    status("Checking listening ports and active network sockets")
    say("Saving listening ports, established TCP connections, and socket ownership to the log.")
    section("Listening TCP Ports")
    if have("lsof"):
        shell("lsof -nP -iTCP -sTCP:LISTEN", sudo=True, timeout=30, long=True, message="Collecting listening TCP ports")
    else:
        shell("netstat -anp tcp | grep LISTEN || true", timeout=20)
    section("Established TCP Connections")
    shell("netstat -anp tcp | grep ESTABLISHED | head -n 100 || true", timeout=20)
    section("Open Network Sockets")
    if have("lsof"):
        shell(
            "lsof -nP -iTCP -iUDP | head -n 250",
            sudo=True, timeout=30, long=True, message="Collecting socket ownership details",
        )
    else:
        log("lsof not found.")
    ok()


def collect_recent_network_logs():
    status("Searching recent logs for VPN, filter, proxy, DNS, and firewall activity")
    say("Querying unified logs for signs of VPN, Network Extension, DNS proxy, firewall, or filter involvement.")
    section("Recent Network, VPN, Filter, Firewall, and Proxy Logs")
    predicate = (
        "process CONTAINS[c] 'socketfilterfw' OR "
        "process CONTAINS[c] 'networkextension' OR "
        "subsystem CONTAINS[c] 'com.apple.networkextension' OR "
        "eventMessage CONTAINS[c] 'filter' OR "
        "eventMessage CONTAINS[c] 'vpn' OR "
        "eventMessage CONTAINS[c] 'utun' OR "
        "eventMessage CONTAINS[c] 'proxy' OR "
        "eventMessage CONTAINS[c] 'dns' OR "
        "eventMessage CONTAINS[c] 'firewall'"
    )
    shell(
        f"log show --last 2h --style compact --predicate \"{predicate}\" 2>/dev/null | tail -n 300 || true",
        timeout=90, long=True,
    )
    ok()


def collect_summary(services, tunnels):
    status("Writing final collection summary")
    say("Recording a compact summary and final log location.")
    section("Summary")
    log(f"Tunnel/VPN-like interfaces detected: {len(tunnels)}")
    log(f"Network services detected: {len(services)}")
    log(f"Output file: {OUTFILE}")
    ok()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    global LOG_FH
    if platform.system() != "Darwin":
        fail_screen("This script is intended to run only on macOS.")
        return 1
    try:
        LOG_FH = OUTFILE.open("w", encoding="utf-8")
    except OSError as err:
        fail_screen(f"Unable to open log file: {err}")
        return 1
    banner()
    log("macscope diagnostic collection")
    log(f"Started: {datetime.datetime.now().isoformat(timespec='seconds')}")
    log(f"Log file: {OUTFILE}")
    try:
        collect_run_context()
        services, tunnels = collect_network_overview()
        collect_system_extensions_and_profiles()
        collect_dns_and_proxy(services)
        collect_smb_config_files()
        collect_smb_mounts_and_shares()
        collect_smb_processes_and_files()
        collect_smb_system_settings()
        collect_smb_directory_snapshot()
        collect_smb_recent_logs()
        collect_smb_client_caches()
        collect_open_smb_volume_handles()
        collect_spotlight_state()
        collect_fsevents_state()
        collect_plugin_inventory()
        collect_tcc_state()
        collect_deep_smb_edge_logs()
        collect_smb_negotiation_summary()
        collect_acl_permission_snapshots()
        collect_finder_network_preferences()
        collect_application_firewall()
        collect_pf_snapshot()
        collect_socket_state()
        collect_recent_network_logs()
        collect_summary(services, tunnels)
    finally:
        log(f"Finished: {datetime.datetime.now().isoformat(timespec='seconds')}")
        LOG_FH.close()
    screen()
    screen("Collection complete.", BOLD + GREEN)
    screen()
    screen(f"Runtime: {elapsed()}", GREEN)
    screen(f"Diagnostic log: {OUTFILE}", GREEN)
    screen("Please share the diagnostic log with the appropriate technical contact.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        print("Interrupted by user. Partial log may still be useful.")
        raise SystemExit(130)
