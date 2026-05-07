import argparse
import json
import sys
import urllib3
import csv
import io
from pathlib import Path
from vastpy import VASTClient

# Suppress InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configuration file location in the user's home directory
CONFIG_FILE = Path.home() / ".vast-viewer.conf"

def get_config(args):
    """Merges config file data with command-line overrides."""
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except json.JSONDecodeError:
            pass
    
    # CLI Overrides take precedence over the config file
    if args.server: config['vast_server'] = args.server
    if args.user: config['vast_user'] = args.user
    if args.password: config['vast_passwd'] = args.password
    
    # Required keys for the VAST Client
    required = ['vast_server', 'vast_user', 'vast_passwd']
    missing = [r for r in required if r not in config]
    if missing:
        print(f"Error: Missing configuration for {', '.join(missing)}")
        print(f"Provide via --server, --user, --password or store them in {CONFIG_FILE}.")
        sys.exit(1)
    return config

def format_output(data, output_type, headers=None):
    """Universal formatter for different output types."""
    if not data:
        if output_type == 'text':
            print("No data returned.")
        return

    # Ensure data is a list for consistent processing
    if isinstance(data, dict):
        # Extract items from API envelopes or handle as a single dictionary
        data_list = data.get('items', [v for v in data.values() if isinstance(v, dict)])
        if not data_list and data:
            data_list = [data]
    else:
        data_list = data if isinstance(data, list) else [data]

    if output_type == 'json':
        print(json.dumps(data, indent=4))
    
    elif output_type == 'csv':
        if not data_list: return
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=data_list[0].keys())
        writer.writeheader()
        writer.writerows(data_list)
        print(output.getvalue())

    elif output_type in ['text', 'table']:
        if not data_list: return
        keys = headers if headers else data_list[0].keys()
        
        header_line = " | ".join([f"{str(k).upper():<15}" for k in keys])
        print(header_line)
        print("-" * len(header_line))
        for item in data_list:
            print(" | ".join([f"{str(item.get(k, 'N/A')):<15}" for k in keys]))

def main():
    parser = argparse.ArgumentParser(
        description="VAST Cluster Configuration Viewer. Credentials can be provided via CLI or stored in ~/.vast-viewer.conf"
    )
    
    # Auth Arguments
    parser.add_argument("--server", help="VAST VMS IP/Hostname")
    parser.add_argument("--user", help="VAST User")
    parser.add_argument("--password", help="VAST Password")
    
    # Output Control
    parser.add_argument("--output", choices=['text', 'json', 'csv', 'table'], default='text', help="Output format")

    # List Commands
    parser.add_argument("--list-policies", action="store_true", help="List all policies")
    parser.add_argument("--list-views", action="store_true", help="List all views")
    parser.add_argument("--list-tenants", action="store_true", help="List all tenants")
    parser.add_argument("--list-vippools", action="store_true", help="List all VIP pools")
    parser.add_argument("--list-activities", action="store_true", help="List recent activity events")
    parser.add_argument("--list-vastdns", action="store_true", help="List DNS configurations")
    parser.add_argument("--list-providers", action="store_true", help="List identity providers")

    # View Commands
    parser.add_argument("--view-policy", action="store_true", help="Detail for a policy (req --id)")
    parser.add_argument("--view", action="store_true", help="Detail for a view (req --id)")
    parser.add_argument("--view-tenant", action="store_true", help="Detail for a tenant (req --id)")
    parser.add_argument("--view-vippools", action="store_true", help="Detail for a VIP Pool (req --id)")
    parser.add_argument("--view-activity", action="store_true", help="Detail for an activity event (req --id)")
    parser.add_argument("--view-vastdns", action="store_true", help="Detail for a DNS configuration (req --id)")
    parser.add_argument("--view-providers", action="store_true", help="Detail for an identity provider (req --id)")
    
    parser.add_argument("--id", type=int, help="Resource ID for detail views")

    args = parser.parse_args()

    # Identify action flags to verify usage
    actions = [a for a in vars(args) if (a.startswith('list_') or a.startswith('view')) and getattr(args, a)]

    # If no action is provided, print help and exit
    if not actions:
        parser.print_help()
        sys.exit(0)

    config = get_config(args)
    client = VASTClient(address=config['vast_server'], user=config['vast_user'], password=config['vast_passwd'])
    client.session.verify = False 

    try:
        # --- LIST OPERATIONS ---
        if args.list_policies:
            format_output(client.viewpolicies.get(), args.output, ['id', 'name'])
        if args.list_views:
            format_output(client.views.get(), args.output, ['id', 'path'])
        if args.list_tenants:
            format_output(client.tenants.get(), args.output, ['id', 'name'])
        if args.list_vippools:
            format_output(client.vippools.get(), args.output, ['id', 'name'])
        if args.list_activities:
            res = client.events.get(page_size=100)
            format_output(res, args.output, ['id', 'severity', 'message'])
        if args.list_vastdns:
            format_output(client.dns.get(), args.output)
        if args.list_providers:
            # Shotgun approach across VMS versions
            for attr in ['active_directories', 'active_directory', 'activedirectories', 'ldap', 'nis', 'providers']:
                try:
                    if hasattr(client, attr):
                        res = getattr(client, attr).get()
                        if res:
                            if args.output == 'text':
                                print(f"\n--- {attr.upper()} ---")
                            format_output(res, args.output)
                except: continue

        # --- VIEW OPERATIONS ---
        detail_map = [
            (args.view_policy, client.viewpolicies),
            (args.view, client.views),
            (args.view_tenant, client.tenants),
            (args.view_vippools, client.vippools),
            (args.view_activity, client.events),
            (args.view_vastdns, client.dns)
        ]
        for flag, resource in detail_map:
            if flag:
                if args.id is None:
                    print(f"Error: Detail views require --id")
                else:
                    format_output(resource[args.id].get(), args.output)

        if args.view_providers:
            if args.id is None:
                print("Error: --view-providers requires --id")
            else:
                found = False
                for attr in ['active_directories', 'active_directory', 'activedirectories', 'ldap', 'nis', 'providers']:
                    try:
                        if hasattr(client, attr):
                            res = getattr(client, attr)[args.id].get()
                            if res:
                                format_output(res, args.output)
                                found = True
                                break
                    except: continue
                if not found:
                    print(f"Provider ID {args.id} not found across identity endpoints.")

    except Exception as e:
        print(f"API Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()