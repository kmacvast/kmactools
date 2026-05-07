#!/usr/bin/env python3
################################################################################
#
# audit_vast_viewer.py
#
# KMac, 20260507
#
# Description: Auditor for the VAST Cluster Configuration Viewer.
# Dynamically gathers metadata to verify all list and view commands.
#
################################################################################

import subprocess, json, random, sys, urllib3, time, argparse
from pathlib import Path
from vastpy import VASTClient

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
CONFIG_FILE = Path.home() / ".vast-viewer.conf"

def get_client():
    with open(CONFIG_FILE, 'r') as f: config = json.load(f)
    c = VASTClient(address=config['vast_server'], user=config['vast_user'], password=config['vast_passwd'])
    c.session.verify = False
    return c

def run_cmd(args):
    start = time.perf_counter()
    p = subprocess.run([sys.executable, "vast-viewer.py"] + args, capture_output=True, text=True)
    return p, time.perf_counter() - start

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-formatting", action="store_true")
    audit_args = parser.parse_args()

    print("="*85)
    print(f"{'COMMAND':<50} | {'TIME':<10} | {'STATUS':<10}")
    print("="*85)

    try:
        client = get_client()
        print("Gathering metadata for detail tests...")
        
        def get_safe_id(resource_call, **kwargs):
            """Robust ID selection that handles 'items' and 'results' envelopes."""
            res = resource_call.get(**kwargs)
            if isinstance(res, dict):
                # Search results, then items, then non-integer values
                data = res.get('results', res.get('items', [v for v in res.values() if isinstance(v, (dict, list))]))
                # If we found a nested list (common in 'results'), use it directly
                if data and isinstance(data, list): pass
                else: data = []
            else: data = res if isinstance(res, list) else []
            return random.choice(list(data))['id'] if data else None

        def find_provider_id(client):
            for attr in ['active_directories', 'active_directory', 'activedirectories', 'ldap', 'nis', 'providers']:
                try:
                    if hasattr(client, attr):
                        res = getattr(client, attr).get()
                        if res:
                            data = res.get('results', res.get('items', [])) if isinstance(res, dict) else res
                            if data: return data[0]['id']
                except: continue
            return None

        test_data = {
            "policy": get_safe_id(client.viewpolicies), "view": get_safe_id(client.views),
            "tenant": get_safe_id(client.tenants), "vippool": get_safe_id(client.vippools),
            "event": get_safe_id(client.events, page_size=50), "dns": get_safe_id(client.dns),
            "provider": find_provider_id(client)
        }
    except Exception as e:
        print(f"FAILED TO INITIALIZE AUDIT: {e}"); return

    # Static Lists
    all_tests = [
        ("--list-policies", None), ("--list-views", None), ("--list-tenants", None),
        ("--list-vippools", None), ("--list-activities", None), ("--list-vastdns", None),
        ("--list-providers", None)
    ]

    # Dynamic Views
    id_map = [
        ("--view-policy", "policy"), ("--view", "view"), 
        ("--view-tenant", "tenant"), ("--view-vippools", "vippool"), 
        ("--view-activity", "event"), ("--view-vastdns", "dns"),
        ("--view-providers", "provider")
    ]
    
    for flag, key in id_map:
        if test_data.get(key) is not None:
            all_tests.append((flag, test_data[key]))

    for flag, target_id in all_tests:
        args = [flag] + (["--id", str(target_id)] if target_id is not None else [])
        res, duration = run_cmd(args)
        status = "✅ PASS" if res.returncode == 0 else "❌ FAIL"
        print(f"vast-viewer.py {' '.join(args)[:48]:<50} | {duration:>8.2f}s | {status}")
        if res.returncode != 0: print(f"   ↳ Error: {res.stdout.strip() or res.stderr.strip()}")
        print("-" * 85)

if __name__ == "__main__": main()