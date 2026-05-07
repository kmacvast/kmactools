import argparse
import json
import sys
import urllib3
from pathlib import Path
from vastpy import VASTClient

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

CONFIG_FILE = Path.home() / ".vast-viewer.conf"

def get_config():
    if not CONFIG_FILE.exists():
        print(f"Error: Configuration file {CONFIG_FILE} not found.")
        sys.exit(1)
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON in {CONFIG_FILE}: {e}")
        sys.exit(1)

def get_client(config):
    """Initializes the VAST Client using the 'bare-bones' method to avoid SSL errors."""
    try:
        client = VASTClient(
            address=config.get('vast_server'),
            user=config.get('vast_user'),
            password=config.get('vast_passwd')
        )
        # Manually disable SSL verification on the internal session object
        client.session.verify = False
        return client
    except Exception as e:
        print(f"Error connecting to VMS: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="VAST Cluster Configuration Viewer")
    
    # List Commands
    parser.add_argument("--list-policies", action="store_true", help="List Policy names/IDs")
    parser.add_argument("--list-views", action="store_true", help="List View paths/IDs")
    parser.add_argument("--list-tenants", action="store_true", help="List Tenant names/IDs")
    parser.add_argument("--list-vippools", action="store_true", help="List VIP Pool names/IDs")
    parser.add_argument("--list-activities", action="store_true", help="List recent activities (via events)")

    # Detail Commands
    parser.add_argument("--view-policy", action="store_true", help="Detail for a policy (req --id)")
    parser.add_argument("--view", action="store_true", help="Detail for a view (req --id)")
    parser.add_argument("--view-tenant", action="store_true", help="Detail for a tenant (req --id)")
    parser.add_argument("--vippool", action="store_true", help="Detail for a VIP Pool (req --id)")
    parser.add_argument("--show-activity", action="store_true", help="Detail for an activity/event (req --id)")
    
    # Global Configs (No ID needed)
    parser.add_argument("--vast-dns", action="store_true", help="Show DNS Configuration")
    parser.add_argument("--vast-providers", action="store_true", help="Show Identity Providers")
    
    parser.add_argument("--id", type=int, help="The ID of the resource")

    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.print_help()
        return

    client = get_client(get_config())

    try:
        # --- LIST OPERATIONS ---
        if args.list_policies:
            print(f"{'ID':<10} | {'Policy Name'}\n" + "-"*40)
            for p in client.viewpolicies.get(): print(f"{p['id']:<10} | {p['name']}")
        
        if args.list_views:
            print(f"{'ID':<10} | {'Path'}\n" + "-"*40)
            for v in client.views.get(): print(f"{v['id']:<10} | {v['path']}")
            
        if args.list_tenants:
            print(f"{'ID':<10} | {'Tenant Name'}\n" + "-"*40)
            for t in client.tenants.get(): print(f"{t['id']:<10} | {t['name']}")
            
        if args.list_vippools:
            print(f"{'ID':<10} | {'VIP Pool Name'}\n" + "-"*40)
            for vp in client.vippools.get(): print(f"{vp['id']:<10} | {vp['name']}")

        if args.list_activities:
            # API responses can include metadata integers; filter them out
            print(f"{'ID':<10} | {'Severity':<12} | {'Message'}\n" + "-"*60)
            res = client.events.get(page_size=100)
            
            # Extract only the objects from envelopes or maps
            if isinstance(res, dict):
                events = res.get('items', [v for v in res.values() if isinstance(v, dict)])
            else:
                events = res if isinstance(res, list) else []

            for e in events: 
                print(f"{e.get('id', 'N/A'):<10} | {e.get('severity', 'N/A'):<12} | {e.get('message', 'N/A')}")

        # --- GLOBAL CONFIGS ---
        if args.vast_dns: 
            print(json.dumps(client.dns.get(), indent=4))

        if args.vast_providers: 
            # Detects identity configuration across various version-specific endpoints
            found = False
            for attr in ['active_directories', 'active_directory', 'activedirectories', 'ldap', 'nis', 'providers']:
                try:
                    res = getattr(client, attr).get()
                    if res:
                        print(f"--- {attr.upper()} Providers ---")
                        print(json.dumps(res, indent=4))
                        found = True
                except Exception:
                    continue
            if not found:
                print("No Identity Providers found.")

        # --- DETAIL OPERATIONS ---
        if args.show_activity:
            if args.id is None:
                print("Error: --show-activity requires --id")
            else:
                print(json.dumps(client.events[args.id].get(), indent=4))

        detail_map = [
            (args.view_policy, client.viewpolicies, "view-policy"),
            (args.view, client.views, "view"),
            (args.view_tenant, client.tenants, "view-tenant"),
            (args.vippool, client.vippools, "vippool")
        ]
        for flag, resource, name in detail_map:
            if flag:
                if args.id is None:
                    print(f"Error: --{name} requires --id")
                else:
                    print(json.dumps(resource[args.id].get(), indent=4))

    except Exception as e:
        print(f"API Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()