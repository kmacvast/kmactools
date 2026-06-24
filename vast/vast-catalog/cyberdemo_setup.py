#!/usr/bin/env python3
################################################################################
#
# Script Name    : cyber-blast-radius-setup.py
# Description    : Walks a target path and updates the access and modification
#                  times (mtime) of a specific subset of files to the current 
#                  system moment.
#
# Purpose        : Sets up and taints environment metadata assets across the
#                  scale namespace to establish a benchmark target for tracking
#                  compromised file timelines.
################################################################################
#
import os
import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Target the mount point where your 40M files live
TARGET_DIR = "/mnt/kmacs-root/vast-catalog/"
MAX_AFFECTED = 5000  # A clean sample size to find inside the 40M total

def main():
    logging.info(f"Starting simulated cyber incident sweep on: {TARGET_DIR}")
    affected_count = 0
    
    for root, _, files in os.walk(TARGET_DIR):
        for file in files:
            file_path = os.path.join(root, file)
            try:
                # Update modification and access times to right now
                os.utime(file_path, None)
                
                # OPTIONAL: If running as root and you want to mimic a specific rogue UID:
                # os.chown(file_path, 9999, -1)
                
                affected_count += 1
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
    print("NOTE: VAST Catalog updates asynchronously via rapid snapshots.")
    print("Please wait 15 to 60 seconds for the catalog to sync before running queries!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()