#!/usr/bin/env bash
################################################################################
#
# Script Name    : linux_find_enhanced.py
# Description    : Brute-force parallelized Linux find script designed to scan
#                  a massive directory tree for a targeted extension signature.
#                  This serves as the "optimized native OS baseline" to benchmark
#                  against VAST Catalog's near-instant database queries.
#
# Optimization   : Splits the top-level directories into parallel execution
#                  streams using xargs. This bypasses single-threaded OS bottlenecks
#                  to flood the VAST storage data plane with metadata requests.
################################################################################

# --- Configuration Variables ---
TARGET_DIR="/mnt/kmacs-root/vast-catalog/"
THREADS=64
TARGET_EXTENSION="locked"

# --- Terminal Colors ---
RESET="\033[0m"
BOLD="\033[1m"
RED="\033[0;31m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
BOLD_RED="\033[1;31m"
BOLD_GREEN="\033[1;32m"
BOLD_YELLOW="\033[1;33m"
BOLD_WHITE="\033[1;37m"

# --- Sanity Check ---
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${BOLD_RED}[ERROR]${RESET} Target directory '$TARGET_DIR' does not exist or is not mounted."
    exit 1
fi

echo -e "${BOLD_GREEN}======================================================================${RESET}"
echo -e "          ${BOLD_WHITE}OPTIMIZED NATIVE LINUX BLAST RADIUS BENCHMARK${RESET}           "
echo -e "${BOLD_GREEN}======================================================================${RESET}"
echo -e "Target Directory : ${CYAN}$TARGET_DIR${RESET}"
echo -e "Parallel Threads : ${YELLOW}$THREADS${RESET}"
echo -e "Target Signature : ${BOLD_YELLOW}*.$TARGET_EXTENSION${RESET}"
echo -e "${BOLD_GREEN}======================================================================${RESET}"
echo -e "Launching brute-force filesystem crawl... Please wait..."
echo -e "----------------------------------------------------------------------"

# Create a temporary file to collect parallel output safely
RESULTS_TMP=$(mktemp)

# Capture high-precision start timestamp
START_TIME=$(date +%s.%N)

# Execute parallel crawl
find "$TARGET_DIR" -mindepth 1 -maxdepth 1 | xargs -P "$THREADS" -I {} find {} -type f -name "*.$TARGET_EXTENSION" > "$RESULTS_TMP"

# Capture high-precision end timestamp
END_TIME=$(date +%s.%N)

# Compute exact duration and comma-formatted counts safely using Python
ELAPSED=$(python3 -c "print(f'{float($END_TIME) - float($START_TIME):.4f}')")
TOTAL_FOUND=$(wc -l < "$RESULTS_TMP")
TOTAL_FOUND_COMMA=$(python3 -c "print(f'{int($TOTAL_FOUND):,}')")

# --- Format and Report Benchmark Results ---
echo -e "----------------------------------------------------------------------"
echo -e "${BOLD_GREEN}Scan Complete.${RESET}"
echo -e "${BOLD_GREEN}======================================================================${RESET}"
echo -e "                               ${BOLD_RED}LINUX OS FILESYSTEM BENCHMARK REPORT${RESET}          "
echo -e "${BOLD_GREEN}======================================================================${RESET}"
echo -e "Filesystem Crawl Time : ${BOLD_RED}${ELAPSED}${RESET} seconds"
echo -e "Total Affected Files  : ${BOLD_RED}${TOTAL_FOUND_COMMA}${RESET}"
echo -e "${BOLD_GREEN}======================================================================${RESET}"

if [ "$TOTAL_FOUND" -gt 0 ]; then
    echo -e "${BOLD_WHITE}AFFECTED ASSETS PREVIEW (First 10 Matches):${RESET}"
    echo -e "----------------------------------------------------------------------"
    # Stripping the target path prefix out of the display lines
    head -n 10 "$RESULTS_TMP" | sed "s|$TARGET_DIR||g"
else
    echo -e " ${BOLD_YELLOW}[!]$RESET Baseline benchmark returned ${GREEN}0${RESET} filesystem results."
fi
echo -e "${BOLD_GREEN}======================================================================${RESET}\n"

# Clean up temp file
rm -f "$RESULTS_TMP"
