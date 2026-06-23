#!/usr/bin/env python3
import os
import sys
import json
import logging
import pandas as pd
import vastdb
from ibis import _

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def load_config():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return json.load(f)

def format_bytes(size_bytes: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def run_security_audit(config: dict, target_logical_path: str):
    logging.info("Opening transaction context to pull POSIX mode frames...")
    
    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )
    
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        # Grabbing target POSIX security columns exposed by the VAST engine
        projection = ['name', 'parent_path', 'size', 'uid', 'owner_name', 'nfs_mode_bits', 'element_type']
        
        reader = catalog_table.select(
            columns=projection,
            predicate=_.parent_path.startswith(target_logical_path)
        )
        table = reader.read_all()
        
    df = table.to_pandas()
    
    # Isolate files for audit
    df_files = df[df['element_type'] == 'FILE'].copy()
    if df_files.empty:
        logging.warning("No files found to analyze. Ensure catalog index is warm.")
        return

    # --- Analysis 1: Bitwise POSIX Mode Calculations ---
    # Standard POSIX mode bits include file-type flags. We mask out the lower 9 bits for permissions.
    df_files['perm_bits'] = df_files['nfs_mode_bits'].fillna(0).astype(int) & 0o777
    
    # Convert permission integer to standard human-readable octal string (e.g., 644, 755)
    df_files['perm_octal'] = df_files['perm_bits'].apply(lambda x: format(x, 'o').zfill(3))
    
    # Identify World-Writable Files (where the final 'other' write bit is enabled: octal mask 002)
    # This is a major corporate compliance trigger.
    world_writable_mask = (df_files['perm_bits'] & 0o002) > 0
    df_exposed = df_files[world_writable_mask]
    
    # --- Analysis 2: Ownership Allocation Profiles ---
    # Group capacity consumption and file counts by the system Owner Name / UID
    owner_summary = df_files.groupby('owner_name').agg(
        file_count=('name', 'count'),
        total_bytes=('size', 'sum')
    ).reset_index()
    owner_summary['readable_size'] = owner_summary['total_bytes'].apply(format_bytes)
    owner_summary = owner_summary.sort_values(by='total_bytes', ascending=False)

    # --- Render Dashboard ---
    print("\n" + "="*80)
    print("                    VAST SECURITY & PERMISSIONS COMPLIANCE REPORT              ")
    print("="*80)
    print(f"Target Scope: {target_logical_path}")
    print("-"*80)
    print("DATA CAPACITY ALLOCATION BY POSIX OWNER:")
    print("-"*80)
    for idx, row in owner_summary.iterrows():
        print(f" Owner: {row['owner_name']:<15} | Files: {row['file_count']:,:<6} | Capacity Used: {row['readable_size']}")
        
    print("-"*80)
    print("RISK DETECTION: WORLD-WRITABLE SECURITY EXPOSURES (Mask o+w):")
    print("-"*80)
    print(f"Total High-Risk Files Located: {len(df_exposed)}")
    if not df_exposed.empty:
        print("\nTop Exposed Candidates:")
        for idx, row in df_exposed.head(5).iterrows():
            print(f" [{row['perm_octal']}] File: {row['name']:<30} | Path: {row['parent_path']}")
    else:
        print(" [✓] Clear. No world-writable exposures discovered in this subtree.")
    print("="*80 + "\n")

def main():
    config = load_config()
    logical_vast_path = "/kmacs/vast-catalog"
    run_security_audit(config, logical_vast_path)

if __name__ == "__main__":
    main()
