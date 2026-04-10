#!/usr/bin/env python3
"""
List all Active Directory configurations from a VAST cluster.

Uses the schema-less vastpy SDK pattern where:
    client.<resource>.get() → GET /api/<resource>/
"""

import os
import urllib3
from vastpy import VASTClient

# Suppress SSL warnings for lab/self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def list_active_directory_configs(address: str, token: str) -> list:
    """
    Retrieve all Active Directory configurations from the VAST cluster.

    Args:
        address: The VMS hostname or IP address.
        token: API token for authentication (VAST 5.3+).

    Returns:
        List of Active Directory configuration dictionaries.
    """
    client = VASTClient(address=address, token=token)

    # Schema-less pattern: client.activedirectory.get() → GET /api/activedirectory/
    return client.activedirectory.get()


def main():
    vms_address = os.environ.get("VMS_ADDRESS", "vast-vms-hostname")
    api_token = os.environ.get("VMS_TOKEN")

    if not api_token:
        print("Error: VMS_TOKEN environment variable is required.")
        print("Usage: export VMS_TOKEN='your-api-token' && python show_ad_configs.py")
        return

    print(f"Connecting to VAST cluster at {vms_address}...")

    try:
        ad_configs = list_active_directory_configs(vms_address, api_token)

        if not ad_configs:
            print("No Active Directory configurations found.")
            return

        print(f"Found {len(ad_configs)} Active Directory configuration(s):\n")
        for config in ad_configs:
            print(f"  ID: {config.get('id')}")
            print(f"  Domain: {config.get('domain_name', 'N/A')}")
            print(f"  Machine Account: {config.get('machine_account_name', 'N/A')}")
            print(f"  State: {config.get('state', 'N/A')}")
            print("-" * 40)

    except Exception as e:
        print(f"Error retrieving AD configurations: {e}")
        raise


if __name__ == "__main__":
    main()
