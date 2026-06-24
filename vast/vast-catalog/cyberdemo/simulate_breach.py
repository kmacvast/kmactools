#!/usr/bin/env python3
################################################################################
#
# Script Name    : cyberdemo_simulate_breach.py
# Description    : Walks a target path randomly and updates the access and 
#                  modification times (mtime) of a specific subset of files.
#
# Purpose        : Simulates a highly scattered rogue process or ransomware 
#                  sweep across distinct organizational paths to maximize the
#                  analytical demo value of the VAST Catalog blast radius query.
################################################################################

import os
import time
import random
import logging

# --- Configuration Settings ---
TARGET_DIR = "/mnt/kmacs-root/vast-catalog/"
MAX_AFFECTED = 5000       # Total files to corrupt across the system
FILES_PER_DIR = 2         # Max files to touch in any single folder before moving on

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def main():
    logging.info(f"Starting scatter-randomized cyber incident sweep on: {TARGET_DIR}")
    affected_count = 0

    for root, dirs, files in os.walk(TARGET_DIR):
        # Trick os.walk: Shuffling dirs in-place forces it down random branch paths
        random.shuffle(dirs)
        
        # Shuffle the files inside this specific directory as well
        random.shuffle(files)

        files_touched_in_this_dir = 0
        for file in files:
            # Enforce the cap per directory to ensure widespread scatter
            if files_touched_in_this_dir >= FILES_PER_DIR:
                break

            file_path = os.path.join(root, file)
            try:
                # Update modification and access times to right now
                os.utime(file_path, None)

                # OPTIONAL: If running as root and you want to mimic a specific rogue UID:
                # os.chown(file_path, 9999, -1)

                affected_count += 1
                files_touched_in_this_dir += 1
                
                if affected_count % 1000 == 0:
                    logging.info(f" -> Rogue activity stamped on {affected_count} files...")
            except Exception:
                # Skip any locked or system-restricted files smoothly
                pass

            if affected_count >= MAX_AFFECTED:
                break
                
        if affected_count >= MAX_AFFECTED:
            break

    logging.info(f"Simulation Complete! Swiftly altered metadata for {affected_count} assets.")
    print("\n" + "="*60)
    print("NOTE: VAST Catalog updates asynchronously via rapid snapshots, it will take <1 minute to update the catalog database.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
