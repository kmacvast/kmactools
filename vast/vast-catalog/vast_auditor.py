#!/usr/bin/env python3
import os
import sys
import json
import logging
from typing import Any, Dict
import pandas as pd
import pyarrow as pa
import urllib3
import vastdb
from ibis import _  # Native VAST database query operator expression builder

# Setup clean stdout logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Suppress insecure lab SSL connection warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def load_config(config_path: str) -> Dict[str, Any]:
    """Loads configuration properties from the environment JSON file."""
    if not os.path.exists(config_path):
        logging.error(f"Configuration file not found at {config_path}.")
        sys.exit(1)
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to parse configuration JSON: {e}")
        sys.exit(1)

def format_bytes(size_bytes: float) -> str:
    """Converts raw byte volumes into human-readable metric string intervals."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"

def query_vast_catalog(config: Dict[str, Any], target_logical_path: str) -> pd.DataFrame:
    """Interfaces with VAST Catalog using server-side predicates to guard client RAM."""
    endpoint = config.get("vast_endpoint")
    access_key = config.get("access_key")
    secret_key = config.get("secret_key")
    
    logging.info(f"Opening ACID transaction context against VAST Database Gateway: {endpoint}")
    
    try:
        session = vastdb.connect(
            endpoint=endpoint, 
            access=access_key, 
            secret=secret_key, 
            ssl_verify=False
        )
        
        with session.transaction() as tx:
            catalog_table = tx.catalog()
            projection_columns = ['name', 'parent_path', 'size', 'mtime', 'extension', 'element_type']
            
            logging.info(f"Pushing down query predicate filter to cluster storage plane: {target_logical_path}")
            
            # The Pushdown: This restricts the query at the cluster layer before it hits your network
            arrow_reader = catalog_table.select(
                columns=projection_columns,
                predicate=_.parent_path.startswith(target_logical_path)
            )
                
            arrow_table = arrow_reader.read_all()
            
        df = arrow_table.to_pandas()
        logging.info(f"Successfully retrieved {len(df)} specific project records from server-side query.")
        return df
        
    except Exception as e:
        logging.error(f"Critical error communicating with VAST Database Engine: {e}")
        sys.exit(1)

def compile_audit_report(df: pd.DataFrame, target_logical_path: str) -> None:
    """Applies analytical data auditing rules over the pre-filtered dataframe."""
    if df.empty:
        logging.warning(f"No catalog records found under path: {target_logical_path}. Ensure Catalog sync has cycled.")
        return

    # Isolate files from directory path nodes
    df_files = df[df['element_type'] == 'FILE'].copy()
    
    if df_files.empty:
        logging.warning("No active files parsed inside directory structure.")
        return
    
    # Calculate file ages from millisecond modification times (mtime)
    df_files['mtime_dt'] = pd.to_datetime(df_files['mtime'], unit='ms', errors='coerce')
    current_time = pd.Timestamp.now()
    df_files['age_days'] = (current_time - df_files['mtime_dt']).dt.days
    
    # --- Rule 1: Historical Cold Data (> 365 Days Unmodified) ---
    cold_mask = df_files['age_days'] > 365
    df_cold = df_files[cold_mask]
    cold_count = len(df_cold)
    cold_size = df_cold['size'].sum()

    # --- Rule 2: Orphaned Scraps (.tmp, .bak, .log) ---
    waste_extensions = ['.tmp', '.bak', '.log']
    scrap_mask = df_files['extension'].isin(waste_extensions) | df_files['name'].str.endswith(tuple(waste_extensions), na=False)
    df_scraps = df_files[scrap_mask]
    scraps_count = len(df_scraps)
    scraps_size = df_scraps['size'].sum()

    # --- Global Summary Calculations ---
    total_files_count = len(df_files)
    total_space_footprint = df_files['size'].sum()
    
    # Combine waste footprints avoiding double counting
    df_combined_waste = df_files[cold_mask | scrap_mask]
    total_waste_size = df_combined_waste['size'].sum()
    total_waste_count = len(df_combined_waste)
    
    # System Efficiency Ratio
    active_clean_space = total_space_footprint - total_waste_size
    efficiency_percentage = (active_clean_space / total_space_footprint * 100) if total_space_footprint > 0 else 100.0

    # Render formatted ASCII reporting matrix block
    print("\n" + "="*80)
    print("                       VAST DATA CATALOG EFFICIENCY REPORT                      ")
    print("="*80)
    print(f"Target Audited Path : {target_logical_path}")
    print(f"Total Files Scanned : {total_files_count:,}")
    print(f"Total Path Footprint: {format_bytes(total_space_footprint)}")
    print("-"*80)
    print("ANALYSIS RULES EVALUATION:")
    print("-"*80)
    print(f" [Rule 1] Historical Cold Data (>365 days unmodified):")
    print(f"          - File Count: {cold_count:,}")
    print(f"          - Space Vol : {format_bytes(cold_size)}")
    print(f" [Rule 2] Orphaned System Scraps (.tmp, .bak, .log):")
    print(f"          - File Count: {scraps_count:,}")
    print(f"          - Space Vol : {format_bytes(scraps_size)}")
    print("-"*80)
    print("ENVIRONMENT SUMMARY METRICS:")
    print("-"*80)
    print(f" Total Actionable Waste Candidates: {total_waste_count:,} files / {format_bytes(total_waste_size)}")
    print(f" Net Optimal Data Footprint       : {format_bytes(active_clean_space)}")
    print(f" Cluster Storage Efficiency Ratio : {efficiency_percentage:.2f}%")
    print("="*80 + "\n")

def main():
    config = load_config(DEFAULT_CONFIG_PATH)
    logical_vast_path = "/kmacs/vast-catalog"
    
    # 1. Pipeline catalog schema into memory using server-side pushdown parameters
    df_catalog = query_vast_catalog(config, logical_vast_path)
    
    # 2. Process metrics
    compile_audit_report(df_catalog, logical_vast_path)

if __name__ == "__main__":
    main()
