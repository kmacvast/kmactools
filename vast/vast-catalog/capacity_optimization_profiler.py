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
    """Converts raw byte counts into human-readable metric strings."""
    if size_bytes == 0:
        return "0.00 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def categorize_size(size_bytes: int) -> str:
    """Categorizes files into specific storage structural brackets."""
    if size_bytes < 4096:
        return "Tiny (< 4KB - Metadata Inlined)"
    elif size_bytes < 65536:
        return "Small (4KB to 64KB)"
    elif size_bytes < 1048576:
        return "Medium (64KB to 1MB)"
    else:
        return "Large (> 1MB)"

def run_optimization_profiler(config: dict, target_logical_path: str):
    logging.info("Opening database transaction to scan block allocation matrix...")
    
    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )
    
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        # Projecting both the logical 'size' and the physical 'used' footprints
        projection = ['name', 'parent_path', 'size', 'used', 'extension', 'element_type']
        
        reader = catalog_table.select(
            columns=projection,
            predicate=_.parent_path.startswith(target_logical_path)
        )
        table = reader.read_all()
        
    df = table.to_pandas()
    df_files = df[df['element_type'] == 'FILE'].copy()
    
    if df_files.empty:
        logging.warning("No files located for block profiling.")
        return

    # --- Calculation 1: Global Storage Efficiency ---
    total_logical = df_files['size'].sum()
    total_physical = df_files['used'].sum()
    
    # Calculate reduction space or padding overhead
    space_delta = total_logical - total_physical
    
    # --- Calculation 2: Structural Size Histogram ---
    df_files['size_bracket'] = df_files['size'].apply(categorize_size)
    
    histogram = df_files.groupby('size_bracket').agg(
        file_count=('name', 'count'),
        logical_bytes=('size', 'sum'),
        physical_bytes=('used', 'sum')
    ).reset_index()
    
    # Order brackets logically for clean reading
    bracket_order = {
        "Tiny (< 4KB - Metadata Inlined)": 1,
        "Small (4KB to 64KB)": 2,
        "Medium (64KB to 1MB)": 3,
        "Large (> 1MB)": 4
    }
    histogram['sort_key'] = histogram['size_bracket'].map(bracket_order)
    histogram = histogram.sort_values('sort_key')

    # --- Render Dashboard ---
    print("\n" + "="*80)
    print("                 VAST CAPACITY PROFILE & DATA STRUCTURE REPORT          ")
    print("="*80)
    print(f"Target Subtree    : {target_logical_path}")
    print(f"Global Logical Size: {format_bytes(total_logical)}")
    print(f"Global Physical Used: {format_bytes(total_physical)}")
    print(f"Net Block Delta   : {format_bytes(space_delta)}")
    print("-"*80)
    print("FILE SIZE DISTRIBUTION & BLOCK ALLOCATION MATRIX:")
    print("-"*80)
    
    for idx, row in histogram.iterrows():
        count_str = f"{row['file_count']:,}"
        log_str = format_bytes(row['logical_bytes'])
        phys_str = format_bytes(row['physical_bytes'])
        
        print(f" Bracket : {row['size_bracket']:<32}")
        print(f"          - File Count    : {count_str:<8}")
        print(f"          - Logical Volume: {log_str:<12} | Physical Allocated: {phys_str}")
        print("-" * 50)
    print("="*80 + "\n")

def main():
    config = load_config()
    logical_vast_path = "/kmacs/vast-catalog"
    run_optimization_profiler(config, logical_vast_path)

if __name__ == "__main__":
    main()
