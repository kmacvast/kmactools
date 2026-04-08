#!/usr/bin/env python3
################################################################################
# Script Name:    vast-du.py
# Description:    Queries the VAST Data REST API to retrieve the Data Reduction 
#                 Ratio (DRR) and capacity metrics for specific directory paths.
#                 Supports recursive child discovery and multiple output formats.
#                 Reads defaults from ~/.vastconf if available.
#                 
# Author:         KMac kmac@vastdata.com
# Created:        2026-04-07
# Version:        2.0.0
# 
# Dependencies:   - Python 3.x
#                 - requests library (pip install requests)
################################################################################

import argparse
import requests
import json
import getpass
import os
import sys
import csv
from urllib3.exceptions import InsecureRequestWarning

# Suppress SSL warnings for self-signed certificates
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

CONFIG_PATH = os.path.expanduser("~/.vastconf")

def load_config():
    """Loads configuration from ~/.vastconf if it exists."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not parse {CONFIG_PATH}: {e}")
    return {}

def get_subdirectories(vms_ip, user, pwd, path, tenant):
    """Fetches immediate subdirectories to support the --children flag."""
    url = f"https://{vms_ip}/api/folders/"
    params = {'path': path.rstrip('/'), 'tenant_name': tenant}
    try:
        response = requests.get(url, auth=(user, pwd), params=params, verify=False, timeout=20)
        response.raise_for_status()
        # Filter for directories and build full logical paths
        return [os.path.join(path, item['name']) for item in response.json() if item.get('is_dir')]
    except Exception:
        return []

def get_drr(vms_ip, user, pwd, directory, tenant):
    """Queries the VAST API for capacity estimation of a specific path and tenant."""
    url = f"https://{vms_ip}/api/capacity/capacity_estimation/"
    clean_path = directory.rstrip('/')
    
    params = {
        'path': clean_path,
        'tenant_name': tenant
    }
    
    try:
        response = requests.get(
            url, 
            auth=(user, pwd), 
            params=params, 
            verify=False,
            timeout=60
        )
        
        if response.status_code == 401:
            return {"path": directory, "error": "Authentication Failed"}
        if response.status_code == 404:
            return {"path": directory, "error": "Resource Not Found"}
            
        response.raise_for_status()
        raw_data = response.json()
        
        if clean_path in raw_data:
            stats = raw_data[clean_path].get('capacity', [0, 0, 0])
            
            # VAST Capacity List Index: [0: Unique, 1: Physical, 2: Logical]
            unique_b   = stats[0]
            physical_b = stats[1]
            logical_b  = stats[2]
            
            drr = logical_b / physical_b if physical_b > 0 else 1.0
            
            return {
                "path": clean_path,
                "logical_gib": round(logical_b / (1024**3), 2),
                "physical_gib": round(physical_b / (1024**3), 2),
                "unique_gib": round(unique_b / (1024**3), 2),
                "drr": round(drr, 2)
            }
        else:
            return {"path": directory, "error": "Path key not found in API response"}

    except Exception as e:
        return {"path": directory, "error": str(e)}

def main():
    config = load_config()

    parser = argparse.ArgumentParser(
        description="VAST Data Reduction Report & Discovery Tool"
    )
    
    # Required/Input Arguments
    parser.add_argument("-d", "--directories", nargs='+', required=True, help="VAST logical paths")
    parser.add_argument("-c", "--children", action="store_true", help="Discover and report on immediate subdirectories")
    
    # Output Control
    parser.add_argument("-o", "--output", choices=['text', 'json', 'csv'], default='text', help="Output format (default: text)")

    # Connection Defaults
    parser.add_argument("-t", "--tenant", default=config.get("tenant"), required=not config.get("tenant"), help="VAST Tenant name")
    parser.add_argument("--vms", default=config.get("vms"), required=not config.get("vms"), help="VAST Management Server FQDN/IP")
    parser.add_argument("--user", default=config.get("user"), required=not config.get("user"), help="VAST User Name")
    parser.add_argument("-p", "--password", help="VAST Password override")

    args = parser.parse_args()
    password = args.password or config.get("password") or getpass.getpass(f"Password for {args.user}: ")

    # 1. Handle Path Discovery
    final_path_list = []
    for p in args.directories:
        final_path_list.append(p)
        if args.children:
            final_path_list.extend(get_subdirectories(args.vms, args.user, password, p, args.tenant))
    
    # Remove duplicates and sort for a clean report
    final_path_list = sorted(list(set(final_path_list)))

    # 2. Gather Data
    results = []
    for path in final_path_list:
        results.append(get_drr(args.vms, args.user, password, path, args.tenant))

    # 3. Handle Output Formats
    if args.output == 'json':
        print(json.dumps(results, indent=4))
    
    elif args.output == 'csv':
        writer = csv.DictWriter(sys.stdout, fieldnames=["path", "logical_gib", "physical_gib", "unique_gib", "drr", "error"])
        writer.writeheader()
        for row in results:
            # Ensure error key exists for rows that succeeded
            if "error" not in row: row["error"] = ""
            writer.writerow(row)

    else:
        # Default Text Table
        print(f"\nVAST Data Reduction Report | VMS: {args.vms} | Tenant: {args.tenant} | User: {args.user}")
        header = f"{'Directory Path':<50} | {'Logical':>10} | {'Phys':>10} | {'Unique':>10} | {'DRR':>8}"
        print(f"{'-' * len(header)}")
        print(header)
        print(f"{'-' * len(header)}")

        for r in results:
            if "error" in r:
                print(f"{r['path']:<50} | Error: {r['error']}")
            else:
                path_str = r['path']
                # Truncate very long paths for the table view
                if len(path_str) > 50: path_str = "..." + path_str[-47:]
                
                print(f"{path_str:<50} | {r['logical_gib']:>7.2f} GiB | {r['physical_gib']:>7.2f} GiB | {r['unique_gib']:>7.2f} GiB | {r['drr']:>7.2f}:1")
        print(f"{'-' * len(header)}\n")

if __name__ == "__main__":
    main()