#!/usr/bin/env python3
import os
import sys
import json
import vastdb

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def main():
    if not os.path.exists(DEFAULT_CONFIG_PATH):
        print("Config file not found.")
        sys.exit(1)
        
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        config = json.load(f)
        
    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )
    
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        # Direct property lookup provided by VAST DB
        schema = catalog_table.arrow_schema
        
    print("\n" + "="*60)
    print("               AVAILABLE VAST CATALOG COLUMNS              ")
    print("="*60)
    for field in schema:
        print(f" Column Name: {field.name:<22} | Type: {str(field.type)}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
