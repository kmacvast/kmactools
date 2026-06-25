#!/usr/bin/env python3
################################################################################
#
# Script Name    : check_specific_files_raw.py
# Description    : Raw metadata dump tool. Pulls matching database records 
#                  and outputs the unformatted, raw data blocks directly
#                  from the catalog transaction with zero translation layers.
#
################################################################################

import os
import json
import pandas as pd
import vastdb
from ibis import _

# --- Configuration Settings ---
TARGET_EXTENSION = "locked"  
CATALOG_PATH_PREFIX = "/kmacs/vast-catalog"
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

# The precise names we want to inspect raw
TARGET_NAMES = [
    "n02395406_boxes.txt.locked",
    "207..locked",
    "n03544143_boxes.txt.locked",
    "25..locked",
    "225..locked",
    "10..locked",
    "n02074367_242.JPEG.locked",
    "1..locked",
    "4..locked"
]

def load_config():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return json.load(f)

def main():
    config = load_config()

    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )

    # Fetch raw data directly from the table
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        reader = catalog_table.select(
            columns=['name', 'parent_path', 'mtime', 'size', 'uid', 'extension'],
            predicate=(
                (_.parent_path.startswith(CATALOG_PATH_PREFIX)) &
                (_.extension == TARGET_EXTENSION)
            )
        )
        table = reader.read_all()

    df = table.to_pandas()

    print("\n======================= RAW DATABASE TRANSACTION ROWS =======================")
    if df.empty:
        print("Empty DataFrame: The database returned 0 records matching the extension.")
    else:
        # Filter the raw data down to your target list
        raw_matches = df[df['name'].isin(TARGET_NAMES)]
        
        if raw_matches.empty:
            print("No raw rows found matching the targeted names list inside the 'locked' dataset.")
        else:
            # Enforce raw presentation modes across wide terminals
            pd.set_option('display.max_columns', None)
            pd.set_option('display.max_colwidth', None)
            pd.set_option('display.width', 1000)
            
            print(raw_matches.to_string(index=False))
            
    print("==============================================================================\n")

if __name__ == "__main__":
    main()
