#!/usr/bin/env python3
################################################################################
#
# Script Name    : restore_breach.py
# Description    : Bypasses filesystem crawling by using VAST Catalog to 
#                  instantly map out all compressed '.locked' assets. Deploys
#                  parallel workers to unzip and restore files back to normal.
#                  
# Optimization   : Gracefully handles asynchronous catalog lag by verifying if
#                  the active data plane has already been restored by an alternate
#                  process, ensuring a clean demo presentation.
#
################################################################################

import os
import json
import time
import zipfile
import logging
import queue
import vastdb
from concurrent.futures import ThreadPoolExecutor
from ibis import _

# --- Configuration Settings ---
TARGET_EXTENSION = "locked"  
CATALOG_PATH_PREFIX = "/kmacs/vast-catalog"
TARGET_DIR = "/mnt/kmacs-root/vast-catalog/"
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

# --- Standard Terminal Colors ---
RESET           = "\033[0m"
RED             = "\033[0;31m"
GREEN           = "\033[0;32m"
YELLOW          = "\033[0;33m"
CYAN            = "\033[0;36m"
BOLD_RED        = "\033[1;31m"
BOLD_GREEN      = "\033[1;32m"
BOLD_YELLOW     = "\033[1;33m"
BOLD_WHITE      = "\033[1;37m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Thread-safe queue to catch true error details
error_log_queue = queue.Queue()

def load_config():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return json.load(f)

def restore_file(row):
    """Worker task to unzip the payload or verify if the original is already present."""
    db_path = row['parent_path']
    file_name = row['name']
    
    # Translate database path to local mount path alignment
    relative_path = db_path.removeprefix(CATALOG_PATH_PREFIX).lstrip("/")
    local_dir = os.path.join(TARGET_DIR, relative_path)
    locked_file_path = os.path.join(local_dir, file_name)
    
    # Deduce what the original healthy filename should be
    original_file_path = locked_file_path.removesuffix("." + TARGET_EXTENSION)
    
    # Check if an external process or re-seeder already fixed the data plane
    if not os.path.exists(locked_file_path):
        if os.path.exists(original_file_path):
            return "ALREADY_HEALTHY"
        else:
            error_log_queue.put({
                "file": file_name,
                "expected_path": locked_file_path,
                "error": "Asset missing: Neither the compressed payload nor the original file exists."
            })
            return "FAILED"
        
    try:
        # Extract original file contents out of the zip container
        with zipfile.ZipFile(locked_file_path, 'r') as zipf:
            zipf.extractall(local_dir)
        # Purge the ransomware signature container
        os.remove(locked_file_path)
        return "RESTORED"
    except Exception as e:
        error_log_queue.put({
            "file": file_name,
            "expected_path": locked_file_path,
            "error": str(e)
        })
        return "FAILED"

def main():
    config = load_config()
    logging.info("Querying VAST Catalog database to locate targeted assets...")

    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )

    # --- Step 1: Instant Database Index Lookup ---
    start_timer = time.perf_counter()
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        reader = catalog_table.select(
            columns=['name', 'parent_path'],
            predicate=(
                (_.parent_path.startswith(CATALOG_PATH_PREFIX)) &
                (_.extension == TARGET_EXTENSION)
            )
        )
        table = reader.read_all()

    df = table.to_pandas()
    query_elapsed = time.perf_counter() - start_timer
    
    if df.empty:
        print(f"\n{BOLD_YELLOW}[!] No compromised '*.{TARGET_EXTENSION}' files found to restore.{RESET}\n")
        return

    print(f" -> Found {len(df):,} encrypted assets via catalog index in {query_elapsed:.4f} seconds.")
    logging.info("Spawning multi-threaded rollback workers to process data plane recovery...")

    # --- Step 2: Parallelized Data Plane Processing ---
    restore_start = time.perf_counter()
    
    restored_count = 0
    already_healthy_count = 0
    failed_count = 0

    with ThreadPoolExecutor(max_workers=32) as executor:
        results = executor.map(restore_file, [row for _, row in df.iterrows()])
        for status in results:
            if status == "RESTORED":
                restored_count += 1
            elif status == "ALREADY_HEALTHY":
                already_healthy_count += 1
            else:
                failed_count += 1

    restore_elapsed = time.perf_counter() - restore_start
    total_successful_resolutions = restored_count + already_healthy_count

    # --- Step 3: Clean Metric Reporting ---
    print("\n" + f"{BOLD_GREEN}" + "="*90 + f"{RESET}")
    print(f"               {BOLD_GREEN}VAST CATALOG: INCIDENT ROLLBACK & RECOVERY{RESET}          ")
    print(f"{BOLD_GREEN}" + "="*90 + f"{RESET}")
    print(f"Database Query Mapping Time  : {GREEN}{query_elapsed:.4f}{RESET} seconds")
    print(f"Data Plane Verification Time : {GREEN}{restore_elapsed:.2f}{RESET} seconds")
    print(f"Active Files Remediated      : {BOLD_WHITE}{restored_count:,}{RESET}")
    print(f"Verified Safe (Pre-Restored) : {CYAN}{already_healthy_count:,}{RESET}")
    print(f"Total Verified Healthy Assets: {BOLD_GREEN}{total_successful_resolutions:,} / {len(df):,}{RESET}")
    print(f"{BOLD_GREEN}" + "="*90 + f"{RESET}")
    
    if failed_count == 0:
        print(f" {BOLD_GREEN}[+]{RESET} Data remediation complete! All assets confirmed secure on the data plane.")
        print(f"     (Note: VAST Catalog view will reflect changes upon next scheduled snapshot flush.)")
        print(f"{BOLD_GREEN}" + "="*90 + f"\n")
    else:
        print(f" {BOLD_RED}[!]{RESET} Warning: Remediation encountered {failed_count} processing failures.")
        print(f"{BOLD_GREEN}" + "="*90 + f"\n")
        
        # --- Step 4: Active Diagnostic Error Presentation ---
        print(f"{BOLD_RED}CRITICAL PATH DIAGNOSTIC ERROR REPORT (First 3 Failures):{RESET}")
        print("="*90)
        printed_errors = 0
        while not error_log_queue.empty() and printed_errors < 3:
            err = error_log_queue.get()
            print(f"  TARGET FILE   : '{err['file']}'")
            print(f"  COMPUTED PATH : '{err['expected_path']}'")
            print(f"  SYSTEM ERROR  :  {RED}{err['error']}{RESET}")
            print("-"*90)
            printed_errors += 1

if __name__ == "__main__":
    main()
