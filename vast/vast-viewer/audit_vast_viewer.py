import subprocess
import json
import random
import sys
import urllib3
import time
from pathlib import Path
from vastpy import VASTClient

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_FILE = Path.home() / ".vast-viewer.conf"

def get_client():
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    c = VASTClient(address=config['vast_server'], user=config['vast_user'], password=config['vast_passwd'])
    c.session.verify = False
    return c

def run_cmd(args):
    """Executes the viewer script and returns result with timing."""
    start_time = time.perf_counter()
    process = subprocess.run(
        [sys.executable, "vast-viewer.py"] + args,
        capture_output=True,
        text=True
    )
    duration = time.perf_counter() - start_time
    return process, duration

def main():
    print("="*85)
    print(f"{'COMMAND':<50} | {'TIME':<10} | {'STATUS':<10}")
    print("="*85)

    try:
        client = get_client()
        print("Gathering metadata for detail tests...")
        
        def get_safe_id(resource_call):
            """Filters out metadata integers from API envelopes before picking an ID"""
            res = resource_call.get() if not isinstance(resource_call, list) else resource_call
            
            # If it's a dict, it might have metadata. Filter for dict values only.
            if isinstance(res, dict):
                data = res.get('items', [v for v in res.values() if isinstance(v, dict)])
            else:
                data = res if isinstance(res, list) else []
                
            return random.choice(data)['id'] if data else None

        test_data = {
            "policy": get_safe_id(client.viewpolicies),
            "view": get_safe_id(client.views),
            "tenant": get_safe_id(client.tenants),
            "vippool": get_safe_id(client.vippools),
            "event": get_safe_id(client.events)
        }
    except Exception as e:
        print(f"FAILED TO INITIALIZE AUDIT: {e}")
        return

    all_tests = [
        ("--list-policies", None), ("--list-views", None), ("--list-tenants", None),
        ("--list-vippools", None), ("--list-activities", None), ("--vast-dns", None),
        ("--vast-providers", None)
    ]

    id_map = [
        ("--view-policy", "policy"), ("--view", "view"), 
        ("--view-tenant", "tenant"), ("--vippool", "vippool"), 
        ("--show-activity", "event")
    ]
    
    for flag, key in id_map:
        if test_data.get(key):
            all_tests.append((flag, test_data[key]))

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