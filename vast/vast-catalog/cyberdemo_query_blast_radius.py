#!/usr/bin/env python3
################################################################################
#
# Script Name    : cyberdemo_query_blast_radius.py
# Description    : Bypasses standard filesystem traversal completely to query
#                  the VAST database table directly. Applies a server-side
#                  pushdown filter to identify every file modified within a
#                  specific timeframe under a target path.
#
# Strategy       : Leverages VAST Catalog to run near-instant metadata inquiries
#                  at scale without dragging down active data-plane performance.
################################################################################
#
import os
import json
import time
import logging
import vastdb
from ibis import _

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def load_config():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return json.load(f)

def main():
    config = load_config()
    logging.info("Opening database transaction to VAST Catalog...")
    
    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )
    
    # Define our 10-minute blast radius window
    # VAST Catalog tracks epoch timestamps in milliseconds
    ten_mins_ago_ms = int(time.time() - 600) * 1000
    
    start_timer = time.perf_counter()
    
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        projection = ['name', 'parent_path', 'mtime', 'size', 'uid']
        
        # Blazing fast database pushdown query
        reader = catalog_table.select(
            columns=projection,
            predicate=(
                (_.parent_path.startswith("/kmacs/vast-catalog")) & 
                (_.mtime >= ten_mins_ago_ms)
                # Alternative syntax if you filtered by UID: (_.uid == 9999)
            )
        )
        table = reader.read_all()
        
    df = table.to_pandas()
    elapsed = time.perf_counter() - start_timer
    
    print("\n" + "="*80)
    print("           VAST CATALOG: CYBER-INCIDENT BLAST RADIUS REPORT          ")
    print("="*80)
    print(f"Database Query Time : {elapsed:.4f} seconds")
    print(f"Total Affected Files: {len(df)}")
    print("-"*80)
    
    if not df.empty:
        print("First 10 Compromised Assets Located:")
        for idx, row in df.head(10).iterrows():
            print(f" FILE: {row['name']:<30} | UID: {row['uid']:<5} | PATH: {row['parent_path']}")
    else:
        print(" [!] Blast radius query returned 0 results.")
        print("     Make sure your background VAST Catalog snapshot sync interval has cycled.")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()