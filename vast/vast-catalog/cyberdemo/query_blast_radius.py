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

import os
import json
import time
import datetime
import logging
import vastdb
from ibis import _

# --- Configuration Settings ---
LOOKBACK_MINUTES = 15
CATALOG_PATH_PREFIX = "/kmacs/vast-catalog"
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

# --- Standard Terminal Colors (Regular) ---
RESET           = "\033[0m"
BLACK           = "\033[0;30m"
RED             = "\033[0;31m"
GREEN           = "\033[0;32m"
YELLOW          = "\033[0;33m"
BLUE            = "\033[0;34m"
MAGENTA         = "\033[0;35m"
CYAN            = "\033[0;36m"
WHITE           = "\033[0;37m"
LIGHT_YELLOW    = "\033[93m"

# --- High-Contrast Colors (Bold) ---
BOLD            = "\033[1m"
BOLD_BLACK      = "\033[1;30m"
BOLD_RED        = "\033[1;31m"
BOLD_GREEN      = "\033[1;32m"
BOLD_YELLOW     = "\033[1;33m"
BOLD_BLUE       = "\033[1;34m"
BOLD_MAGENTA    = "\033[1;35m"
BOLD_CYAN       = "\033[1;36m"
BOLD_WHITE      = "\033[1;37m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

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

    # Define our blast radius window using a native Python datetime from global variable.
    # Ibis automatically converts this to match the database's timestamp(9) column.
    time_window = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=LOOKBACK_MINUTES)

    # --- 1. Query for Affected Blast-Radius Files ---
    start_timer = time.perf_counter()

    with session.transaction() as tx:
        catalog_table = tx.catalog()
        projection = ['name', 'parent_path', 'mtime', 'size', 'uid']

        # Blazing fast database pushdown query
        reader = catalog_table.select(
            columns=projection,
            predicate=(
                (_.parent_path.startswith(CATALOG_PATH_PREFIX)) &
                (_.mtime >= time_window)
            )
        )
        table = reader.read_all()

    df = table.to_pandas()
    elapsed = time.perf_counter() - start_timer

    # Calculate the actual exact window and elapsed duration of when the files changed
    if not df.empty:
        start_dt = df['mtime'].min()
        end_dt = df['mtime'].max()
        actual_start_time = start_dt.strftime('%d/%m/%Y %H:%M:%S')
        actual_end_time = end_dt.strftime('%d/%m/%Y %H:%M:%S')
        duration_seconds = int((end_dt - start_dt).total_seconds())
    else:
        actual_start_time = "N/A"
        actual_end_time = "N/A"
        duration_seconds = 0

    # --- 2. Stream-Count Total Files under Path for Scale Context ---
    logging.info("Calculating total dataset file count for scale comparison...")
    total_files = 0
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        total_reader = catalog_table.select(
            columns=['name'],
            predicate=(_.parent_path.startswith(CATALOG_PATH_PREFIX))
        )
        # Iterating directly over the reader processes data block-by-block safely
        for batch in total_reader:
            total_files += batch.num_rows

    # --- 3. Generate Report Output ---
    print("\n" + f"{BOLD_GREEN}" + "="*90 + f"{RESET}")
    print(f"           {BOLD_GREEN}CYBER-INCIDENT BLAST RADIUS REPORT{RESET}          ")
    print(f"{BOLD_GREEN}" + "="*90 + f"{RESET}")
    print(f"Target Prefix Path  : {CYAN}{CATALOG_PATH_PREFIX}{RESET}")
    print(f"Lookback Window     : Last {YELLOW}{LOOKBACK_MINUTES}{RESET} minutes")
    print(f"Database Query Time : {GREEN}{elapsed:.4f}{RESET} seconds")

    # Highlight affected count in Bold Red to indicate a breach, total files in Bold Cyan
    print(f"Total Affected Files: {BOLD_RED}{len(df):,}{RESET}")
    print(f"Total Files         : {BOLD_CYAN}{total_files:,}{RESET}")
    print(f"{GREEN}" + "-" * 90 + f"{RESET}")
    print(f"  {BOLD_RED}ALERT!{RESET}")
    print(f"  The assets listed below are flagged as comprimised due to ")
    print(f"  abnormal write modifications between:")
    print(f"  {LIGHT_YELLOW}{actual_start_time}{RESET} UTC and {LIGHT_YELLOW}{actual_end_time}{RESET} UTC ({BOLD_WHITE}{duration_seconds:,} seconds{RESET}) ")
    print(f"{BOLD_GREEN}" + "="*90 + f"{RESET}")

    if not df.empty:
        # Table headers bolded
        print(f"{RESET}{'FILE NAME':<20} | {'UID':<5} | {'MODIFIED TIME (UTC)':<20} | {'PATH'}{GREEN}")
        print("-"*90)
        for idx, row in df.head(10).iterrows():
            mtime_clean = row['mtime'].strftime('%d/%m/%Y %H:%M:%S')

            # Format parts cleanly wrapped around padded boundaries (Dates colored LIGHT_YELLOW)
            f_name = f"{BOLD_WHITE}{row['name']:<20}{RESET}"
            f_uid  = f"{row['uid']:<5}"
            f_time = f"{LIGHT_YELLOW}{mtime_clean:<20}{RESET}"
            f_path = f"{row['parent_path']}"

            print(f"{f_name} | {f_uid} | {f_time} | {f_path}")
    else:
        print(f" {BOLD_YELLOW}[!]{RESET} Blast radius query returned {GREEN}0{RESET} results.")
        print("     No files have been modified within the lookback window.")
    print(f"{BOLD_GREEN}" + "="*90 + f"{RESET}\n")

if __name__ == "__main__":
    main()
