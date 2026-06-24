#!/usr/bin/env bash
################################################################################
#
# Script Name    : cyberdemo_parallel_linux_find.sh
# Description    : Brute-force parallelized Linux find script designed to scan
#                  a massive directory tree for recently modified files. This
#                  serves as the "optimized native OS baseline" to benchmark
#                  against VAST Catalog's near-instant database queries.
#
# Optimization   : Splits the top-level directories into parallel execution
#                  streams using xargs. This bypasses single-threaded OS bottlenecks
#                  to flood the VAST storage data plane with metadata requests.
################################################################################

# --- Configuration Variables ---
TARGET_DIR="/mnt/kmacs-root/vast-catalog/"
THREADS=64
MOD_MINUTES=10

# --- Sanity Check ---
if [ ! -d "$TARGET_DIR" ]; then
    echo "[ERROR] Target directory '$TARGET_DIR' does not exist or is not mounted."
    exit 1
fi

echo "======================================================================"
echo "      OPTIMIZED NATIVE LINUX BLAST RADIUS BENCHMARK SCRIPT           "
echo "======================================================================"
echo "Target Directory : $TARGET_DIR"
echo "Parallel Threads : $THREADS"
echo "Lookback Window  : Last $MOD_MINUTES minutes"
echo "======================================================================"
echo "Launching brute-force filesystem crawl... Please wait..."
echo "----------------------------------------------------------------------"

# --- Executing the Optimized Search ---
# The pipeline is wrapped in a block { ... } so the 'time' utility measures 
# the cumulative duration of the entire operation, from start to finish.
time {
    find "$TARGET_DIR" -mindepth 1 -maxdepth 1 | xargs -P "$THREADS" -I {} find {} -type f -mmin -"$MOD_MINUTES"
}

echo "----------------------------------------------------------------------"
echo "Scan Complete."
echo "======================================================================"