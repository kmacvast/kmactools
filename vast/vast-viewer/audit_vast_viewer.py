import subprocess
import json
import random
import sys
import urllib3
import time
import argparse
from pathlib import Path
from vastpy import VASTClient

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_FILE = Path.home() / ".vast-viewer.conf"

def get_client():
    """Initializes the VAST Client with SSL verification disabled."""
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    c = VASTClient(address=config['vast_server'], user=config['vast_user'], password=config['vast_passwd'])
    c.session.verify = False
    return c

def run_cmd(args):
    """Executes the viewer script and returns result with high-resolution timing."""
    start_time = time.perf_counter()
    process = subprocess.run(
        [sys.executable, "vast-viewer.py"] + args,
        capture_output=True,
        text=True
    )
    duration = time.perf_counter() - start_time
    return process, duration

def main():
    parser = argparse.ArgumentParser(description="Auditor for VAST Configuration Viewer")
    parser.add_argument("--check-formatting", action="store_true", help="Verify JSON, CSV, and Table outputs")
    audit_args = parser.parse_args()

    print("="*85)
    print(f"{'COMMAND':<50} | {'TIME':<10} | {'STATUS':<10}")
    print("="*85)

    try:
        client = get_client()
        print("Gathering metadata for detail tests...")
        
        def get_safe_id(resource_call, **kwargs):
            """Filters out metadata integers from API envelopes before picking a random ID."""
            res = resource_call.get(**kwargs)
            if isinstance(res, dict):
                data = res.get('items', [v for v in res.values() if isinstance(v, dict)])
            else:
                data = res if isinstance(res, list) else []
            return random.choice(data)['id'] if data else None

        # Gather IDs for view tests, including the new DNS metadata
        test_data = {
            "policy": get_safe_id(client.viewpolicies),
            "view": get_safe_id(client.views),
            "tenant": get_safe_id(client.tenants),
            "vippool": get_safe_id(client.vippools),
            "event": get_safe_id(client.events, page_size=50),
            "dns": get_safe_id(client.dns) # Added missed metadata gatherer
        }
    except Exception as e:
        print(f"FAILED TO INITIALIZE AUDIT: {e}")
        return

    # Optional Formatting Checks
    if audit_args.check_formatting:
        print("Running Output Format Checks...")
        for fmt in ['json', 'csv', 'table']:
            res, duration = run_cmd(["--list-tenants", "--output", fmt])
            status = "✅ PASS" if res.returncode == 0 and res.stdout.strip() else "❌ FAIL"
            print(f"Format Check: {fmt:<36} | {duration:>8.2f}s | {status}")
            print("-" * 85)

    # Updated Static Test List with new verbiage
    all_tests = [
        ("--list-policies", None), 
        ("--list-views", None), 
        ("--list-tenants", None),
        ("--list-vippools", None), 
        ("--list-activities", None), 
        ("--list-vastdns", None),      # Updated from --vast-dns
        ("--list-providers", None)     # Updated from --vast-providers
    ]

    # Updated Dynamic Detail Tests with new verbiage
    id_map = [
        ("--view-policy", "policy"), 
        ("--view", "view"), 
        ("--view-tenant", "tenant"), 
        ("--view-vippools", "vippool"), # Updated from --vippool
        ("--view-activity", "event"),   # Updated from --show-activity
        ("--view-vastdns", "dns")       # Added missed DNS detail test
    ]
    
    for flag, key in id_map:
        if test_data.get(key):
            all_tests.append((flag, test_data[key]))

    # Execution Loop
    for flag, target_id in all_tests:
        args = [flag] + (["--id", str(target_id)] if target_id else [])
        res, duration = run_cmd(args)
        status = "✅ PASS" if res.returncode == 0 else "❌ FAIL"
        
        cmd_str = f"vast-viewer.py {' '.join(args)}"
        print(f"{cmd_str[:50]:<50} | {duration:>8.2f}s | {status}")
        
        if res.returncode != 0:
            print(f"   ↳ Error: {res.stdout.strip() or res.stderr.strip()}")
        print("-" * 85)

if __name__ == "__main__":
    main()