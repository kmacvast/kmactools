#!/usr/bin/env python3
################################################################################
#
# Script Name    : simulate_breach.py
# Description    : Advanced multi-threaded cyber incident simulator. Discovers
#                  all top-level directories, deploys parallel attack workers,
#                  dives exactly 3 levels deep via randomized branching, and
#                  compresses assets into encrypted-style binary payloads.
#
# Spice Factor   : High. Replaces targeted source files with compressed
#                  ".locked" ZIP archives to dramatically manipulate layout
#                  metadata signatures for catalog validation.
################################################################################

import os
import time
import random
import logging
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor

# --- Configuration Settings ---
TARGET_DIR = "/mnt/kmacs-root/vast-catalog/"
MAX_AFFECTED = 5150       # Total files to corrupt globally across the system
FILES_PER_DIR = 2         # Max files to encrypt per folder before hopping branches
EXTENSION_SUFFIX = ".locked"

# --- Terminal Colors ---
RESET           = "\033[0m"
CYAN            = "\033[0;36m"
GREEN           = "\033[0;32m"
BOLD_RED        = "\033[1;31m"
BOLD_GREEN      = "\033[1;32m"
BOLD_YELLOW     = "\033[1;33m"
BOLD_WHITE      = "\033[1;37m"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Threading synchronizations
counter_lock = threading.Lock()
stop_event = threading.Event()
affected_count = 0

def lock_and_zip_file(file_path):
    """Safely zips a target file into a new extension and destroys the original."""
    locked_path = file_path + EXTENSION_SUFFIX
    try:
        # Wrap file inside a standard compressed zip payload
        with zipfile.ZipFile(locked_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(file_path, os.path.basename(file_path))
        # Delete original to simulate hostile data manipulation
        os.remove(file_path)
        return True
    except Exception:
        # Clean up partial creations if permissions fail
        if os.path.exists(locked_path):
            os.remove(locked_path)
        return False

def tld_worker(tld_path):
    """Thread execution routine mapped strictly inside a specific TLD namespace."""
    global affected_count
    logging.info(f"Thread worker successfully anchored to TLD: {tld_path}")

    # Safe protection counter to exit if this TLD runs entirely out of files
    empty_consecutive_attempts = 0

    while not stop_event.is_set() and empty_consecutive_attempts < 20:
        # --- Level 2 Navigation ---
        try:
            l2_dirs = [os.path.join(tld_path, d) for d in os.listdir(tld_path) if os.path.isdir(os.path.join(tld_path, d))]
        except Exception:
            l2_dirs = []

        if not l2_dirs:
            subtree_choice = tld_path
        else:
            l2_choice = random.choice(l2_dirs)
            # --- Level 3 Navigation ---
            try:
                l3_dirs = [os.path.join(l2_choice, d) for d in os.listdir(l2_choice) if os.path.isdir(os.path.join(l2_choice, d))]
            except Exception:
                l3_dirs = []
            subtree_choice = random.choice(l3_dirs) if l3_dirs else l2_choice

        # Gather ALL candidate target assets under this specific randomized branch
        subtree_files = []
        try:
            for root, _, files in os.walk(subtree_choice):
                for f in files:
                    if not f.endswith(EXTENSION_SUFFIX):
                        subtree_files.append(os.path.join(root, f))
        except Exception:
            pass

        # If this subtree path is dry, loop back to branch out into an alternative option
        if not subtree_files:
            empty_consecutive_attempts += 1
            continue

        empty_consecutive_attempts = 0 # Reset counter since we have workable assets

        # Absolute scattering: Shuffle the files found across the whole subtree
        random.shuffle(subtree_files)

        dir_touch_count = 0
        for file_path in subtree_files:
            if dir_touch_count >= FILES_PER_DIR:
                break
            if stop_event.is_set():
                return

            # Manage global quota allocation across competing threads
            with counter_lock:
                if affected_count >= MAX_AFFECTED:
                    stop_event.set()
                    return
                affected_count += 1
                current_snapshot_count = affected_count

            # Trigger zip compression swap
            if lock_and_zip_file(file_path):
                dir_touch_count += 1
                if current_snapshot_count % 500 == 0:
                    logging.info(f" -> [!] Spicy ransomware footprint expanded to {current_snapshot_count} assets...")
            else:
                with counter_lock:
                    affected_count -= 1

def main():
    if not os.path.exists(TARGET_DIR):
        logging.error(f"Target directory path not found: {TARGET_DIR}")
        return

    # Phase 1: Dynamically extract all available Top Level Directories (TLDs)
    tlds = [os.path.join(TARGET_DIR, d) for d in os.listdir(TARGET_DIR) if os.path.isdir(os.path.join(TARGET_DIR, d))]

    if not tlds:
        logging.warning("No TLD subdirectories located. Defaulting entire operation scope to mount root.")
        tlds = [TARGET_DIR]

    logging.info(f"Discovered {len(tlds)} isolated Top-Level Directories. Initializing parallel malware simulation...")

    # Phase 2: Deploy thread pool matched to the number of TLDs
    max_workers = len(tlds)
    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        executor.map(tld_worker, tlds)

    elapsed = time.perf_counter() - start_time
    files_per_sec = affected_count / elapsed if elapsed > 0 else 0

    # --- High-Contrast Scannable Summary Report ---
    print("\n" + f"{BOLD_YELLOW}" + "="*90 + f"{RESET}")
    print(f"               {BOLD_YELLOW}CYBER-INCIDENT SIMULATION REPORT{RESET}          ")
    print(f"{BOLD_YELLOW}" + "="*90 + f"{RESET}")
    print(f"Target Directory      : {CYAN}{TARGET_DIR}{RESET}")
    print(f"Parallel Worker Cores : {CYAN}{max_workers:,}{RESET}")
    print(f"Total Assets Mutated  : {BOLD_RED}{affected_count:,}{RESET}")
    print(f"Simulation Runtime    : {GREEN}{elapsed:.2f}{RESET} seconds")
    print(f"Data Mutation Velocity: {BOLD_WHITE}{files_per_sec:.2f}{RESET} files/sec")
    print(f"{BOLD_YELLOW}" + "="*90 + f"{RESET}")
    print(f" {BOLD_RED}[ ALERT ]{RESET} Data plane transformation finalized successfully.")
    print(f"           All designated source files have been compressed and replaced.")
    print(f"           {BOLD_YELLOW}Action Item:{RESET} Allow 30 to 90 seconds for background VAST")
    print(f"           Catalog snapshot ingestion to sync the database index view.")
    print(f"{BOLD_YELLOW}" + "="*90 + f"\n")

if __name__ == "__main__":
    main()
