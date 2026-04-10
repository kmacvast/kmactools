#!/usr/bin/env python3
################################################################################
# Script Name:    vast_get_token.py
# Description:    Exchanges legacy username/password credentials from 
#                 ~/.vastconf for a VAST API Token via the REST API.
#
# Author:         KMac kmac@vastdata.com
# Version:        0.1.0
################################################################################

import os
import json
import urllib3
from vastpy import VASTClient

# Suppress SSL warnings for lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def load_config(config_path="~/.vastconf"):
    """
    Loads VAST configuration from a JSON file.
    
    Args:
        config_path (str): Path to the config file. Defaults to ~/.vastconf.
        
    Returns:
        dict: The parsed configuration data.
    """
    full_path = os.path.expanduser(config_path)
    if not os.path.exists(full_path):
        raise FileNotFoundError(f"Configuration file not found at {full_path}")
        
    with open(full_path, 'r') as f:
        return json.load(f)

def generate_vast_token():
    """
    Authenticates with VMS and generates a new API token for the configured user.
    """
    try:
        # Load context from ~/.vastconf
        conf = load_config()

        vms_addr = conf.get("vms")
        user = conf.get("user")
        password = conf.get("password")

        # FIX: Normalize tenant. If empty string or "default", set to None.
        # This ensures Global Admins (like 'admin') authenticate correctly.
        raw_tenant = conf.get("tenant", "").strip()
        tenant = raw_tenant if raw_tenant and raw_tenant.lower() != "default" else None

        print(f"[*] Authenticating as '{user}' on {vms_addr} (Tenant: {tenant or 'Global/None'})...")

        # Initialize the schema-less client
        client = VASTClient(
            address=vms_addr,
            user=user,
            password=password,
            tenant=tenant
        )

        # Generate the token via schema-less POST
        # Maps to: POST /api/apitokens/
        token_response = client.apitokens.post(owner=user)

        token = token_response.get("token")

        if token:
            print("\n" + "="*40)
            print("SUCCESS: VAST API TOKEN GENERATED")
            print("="*40)
            print(token)
            print("="*40)
            print("\nTip: Export this as VMS_TOKEN or update your ~/.vastconf.")
        else:
            print("[-] Response received, but no token found in payload.")

    except Exception as e:
        print(f"\n[!] ERROR: Failed to generate token.")
        print(f"Details: {e}")

if __name__ == "__main__":
    generate_vast_token()
