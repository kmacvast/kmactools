#!/usr/bin/env python3
################################################################################
#
# vast-viewer.py
#
# KMac, 20260507
#
# Description: VAST Cluster Configuration Viewer.
# Retrieves and displays policies, views, tenants, VIP pools, activities, DNS, 
# and identity providers across various VMS versions.
#
# Note: I’ll add capabilities as I learn recurring tasks. (That’s the point of this TBH)
#
# Usage: python3 vast-viewer.py --list-<resource>
#        python3 vast-viewer.py --view-<resource> --id <ID> [--output <type>]
#
# Credentials: CLI arguments or stored in ~/.vast-viewer.conf.
# Output: Supports text, table, json, and csv formats. Default is JSON.
#
################################################################################

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
    
    if args.server: config['vast_server'] = args.server
    if args.user: config['vast_user'] = args.user
    if args.password: config['vast_passwd'] = args.password
    
    required = ['vast_server', 'vast_user', 'vast_passwd']
    missing = [r for r in required if r not in config]
    if missing:
        print(f"Error: Missing configuration for {', '.join(missing)}")
        print(f"Provide via --server, --user, --password or store in {CONFIG_FILE}.")
        sys.exit(1)
    return config

def format_output(data, output_type, headers=None):
    """Universal formatter for VAST data structures."""
    if data is None or (isinstance(data, (list, dict)) and not data):
        if output_type == 'json':
            print("[]")
        elif output_type == 'text':
            print("No data returned.")
        return

    # Handle API envelopes and detail objects
    if isinstance(data, dict):
        if 'items' in data:
            data_list = data['items']
        elif 'results' in data:
            data_list = data['results']
        elif 'id' in data:
            data_list = [data] # Treat as detail object
        else:
            # Map-style collection: filter out metadata integers
            data_list = [v for v in data.values() if isinstance(v, (dict, list))]
            if not data_list and data: data_list = [data]
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
        description="VAST Cluster Configuration Viewer. Credentials stored in ~/.vast-viewer.conf"
    )
    
    parser.add_argument("--server", help="VAST VMS IP/Hostname")
    parser.add_argument("--user", help="VAST User")
    parser.add_argument("--password", help="VAST Password")
    parser.add_argument("--output", choices=['text', 'json', 'csv', 'table'], default='json', help="Output format")

    # Actions
    parser.add_argument("--list-policies", action="store_true")
    parser.add_argument("--list-views", action="store_true")
    parser.add_argument("--list-tenants", action="store_true")
    parser.add_argument("--list-vippools", action="store_true")
    parser.add_argument("--list-activities", action="store_true")
    parser.add_argument("--list-vastdns", action="store_true")
    parser.add_argument("--list-providers", action="store_true")

    parser.add_argument("--view-policy", action="store_true")
    parser.add_argument("--view", action="store_true")
    parser.add_argument("--view-tenant", action="store_true")
    parser.add_argument("--view-vippools", action="store_true")
    parser.add_argument("--view-activity", action="store_true")
    parser.add_argument("--view-vastdns", action="store_true")
    parser.add_argument("--view-providers", action="store_true")
    
    parser.add_argument("--id", type=int)

    args = parser.parse_args()
    actions = [a for a in vars(args) if (a.startswith('list_') or a.startswith('view')) and getattr(args, a)]
    if not actions:
        parser.print_help()
        sys.exit(0)

    config = get_config(args)
    client = VASTClient(address=config['vast_server'], user=config['vast_user'], password=config['vast_passwd'])
    client.session.verify = False 

    try:
        if args.list_policies: format_output(client.viewpolicies.get(), args.output, ['id', 'name'])
        if args.list_views: format_output(client.views.get(), args.output, ['id', 'path'])
        if args.list_tenants: format_output(client.tenants.get(), args.output, ['id', 'name'])
        if args.list_vippools: format_output(client.vippools.get(), args.output, ['id', 'name'])
        if args.list_activities: 
            format_output(client.events.get(page_size=100), args.output, ['id', 'severity', 'event_message'])
        if args.list_vastdns: format_output(client.dns.get(), args.output)
        
        if args.list_providers:
            all_providers = {} if args.output == 'json' else []
            found_any = False
            for attr in ['active_directories', 'active_directory', 'activedirectories', 'ldap', 'nis', 'providers']:
                try:
                    if hasattr(client, attr):
                        res = getattr(client, attr).get()
                        if res is not None:
                            # Normalize into a list for evaluation
                            items = []
                            if isinstance(res, dict): items = res.get('items', res.get('results', []))
                            elif isinstance(res, list): items = res
                            
                            if items:
                                found_any = True
                                if args.output == 'text':
                                    print(f"\n--- {attr.upper()} ---")
                                    format_output(items, 'text')
                                elif args.output == 'json':
                                    all_providers[attr] = res
                                else:
                                    all_providers.extend(items)
                except: continue
            
            if args.output != 'text':
                format_output(all_providers if found_any else None, args.output)

        detail_map = [
            (args.view_policy, client.viewpolicies), (args.view, client.views),
            (args.view_tenant, client.tenants), (args.view_vippools, client.vippools),
            (args.view_activity, client.events), (args.view_vastdns, client.dns)
        ]
        for flag, resource in detail_map:
            if flag:
                if args.id is None: 
                    print(f"Error: {flag} requires --id"); sys.exit(1)
                format_output(resource[args.id].get(), args.output)

        if args.view_providers:
            if args.id is None: 
                print("Error: --view-providers requires --id"); sys.exit(1)
            found = False
            for attr in ['active_directories', 'active_directory', 'activedirectories', 'ldap', 'nis', 'providers']:
                try:
                    res = getattr(client, attr)[args.id].get()
                    if res: format_output(res, args.output); found = True; break
                except: continue
            if not found: 
                print(f"Provider {args.id} not found."); sys.exit(1)

    except Exception as e:
        print(f"API Error: {e}"); sys.exit(1)

if __name__ == "__main__": main()