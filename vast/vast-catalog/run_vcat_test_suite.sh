#!/usr/bin/env bash
################################################################################
#
# Script Name    : run_vcat_test_suite.sh
# Description    : Comprehensive automated validation harness for vcatalog_tool.py.
#                  Exercises Catalog Plane, VMS REST APIs, and S3 Protocol paths.
#
# Usage          : ./run_vcat_test_suite.sh
#
################################################################################

RESET="\033[0m"
BOLD="\033[1m"
BLUE="\033[0;34m"
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
CYAN="\033[0;36m"
BOLD_WHITE="\033[1;37m"
BOLD_YELLOW="\033[1;33m"
BOLD_CYAN="\033[1;36m"

TOOL_EXEC="./vcatalog_tool.py"
MOUNT_ROOT="/mnt/kmacs-root/vast-catalog"
SAMPLE_FILE=""

if [ ! -x "$TOOL_EXEC" ]; then
    echo -e "[ERROR] $TOOL_EXEC is missing or not marked executable."
    exit 1
fi

resolve_sample_file() {
    local preferred=(
        "${MOUNT_ROOT}/workspace_1/corporate_email/brawner-s/_sent_mail/25.locked"
        "${MOUNT_ROOT}/workspace_1/linux-2.6.11/COPYING"
        "${MOUNT_ROOT}/linux-2.6.11/COPYING"
    )
    local candidate
    for candidate in "${preferred[@]}"; do
        if [ -f "$candidate" ]; then
            SAMPLE_FILE="$candidate"
            return 0
        fi
    done
    if [ -d "$MOUNT_ROOT" ]; then
        SAMPLE_FILE=$(find "$MOUNT_ROOT" -type f -size +0 2>/dev/null | head -n 1)
        if [ -n "$SAMPLE_FILE" ] && [ -f "$SAMPLE_FILE" ]; then
            return 0
        fi
    fi
    return 1
}

print_test_header() {
    local test_num=$1
    local test_title=$2
    local test_cmd=$3

    echo -e "${BOLD_YELLOW}========================================================================================${RESET}"
    echo -e " ${BOLD_WHITE}TEST CONTEXT [${test_num}]: ${BOLD_CYAN}${test_title}${RESET}"
    echo -e " ${BLUE}Executing Command : ${CYAN}${test_cmd}${RESET}"
    echo -e "${BOLD_YELLOW}========================================================================================${RESET}"
}

print_test_footer() {
    echo -e "\n\n"
}

clear
echo -e "${GREEN}========================================================================================${RESET}"
echo -e "                 ${BOLD_WHITE}VAST CATALOG UNIFIED ENGINE EXTENDED DIAGNOSTIC AUDIT HARNESS${RESET}"
echo -e "${GREEN}========================================================================================${RESET}\n"

if resolve_sample_file; then
    echo -e "${CYAN}Resolved sample file:${RESET} ${SAMPLE_FILE}\n"
else
    echo -e "${YELLOW}[WARN] No readable file under ${MOUNT_ROOT}; Tests 8 and 9 will be skipped.${RESET}\n"
fi

# --- TEST 1: Python Regression Code Test Suite ---
CMD="python3 -m unittest test_vcatalog_tool.py"
print_test_header "1" "Python Code Regression Testing (Expanded Mocks & Analytics Math)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 2: Platform Reference Introspection ---
CMD="${TOOL_EXEC} --about"
print_test_header "2" "Internal VAST Platform Documentation & Metrics Glossary Dump" "$CMD"
eval $CMD | head -n 45
print_test_footer

# --- TEST 3: Schema Layout Mapping ---
CMD="${TOOL_EXEC} --show-schema"
print_test_header "3" "VASTDB Database Tabular Arrow Schema Column Property Introspection" "$CMD"
eval $CMD
print_test_footer

# --- TEST 4: Parallel Streaming Capacity Profiling ---
CMD="${TOOL_EXEC} --show-capacity"
print_test_header "4" "Multi-Threaded Data Structural Profiler & Block Size Histogram" "$CMD"
eval $CMD
print_test_footer

# --- TEST 5: Cold File Retention Evaluation ---
CMD="${TOOL_EXEC} --show-cold-files --num-days 180"
print_test_header "5" "Retention Compliance & Multi-Core Waste Tracking (Lookback: 180 Days)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 6: Identity and Owner Profile ---
CMD="${TOOL_EXEC} --analysis-by-owner --uid 1000"
print_test_header "6" "POSIX Identity Capacity Allocation & World-Writable Risk Audit" "$CMD"
eval $CMD
print_test_footer

# --- TEST 7: VMS REST API Three-Pillar Reduction Dashboard ---
CMD="${TOOL_EXEC} --show-data-reduction-rates --directory /kmacs/vast-catalog/workspace_1"
print_test_header "7" "VMS API Core Probe: Unique vs Usable Tiers (Dedup, Similarity, Compression)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 8: Cross-Protocol Path Translation ---
if [ -n "$SAMPLE_FILE" ]; then
    CMD="${TOOL_EXEC} --translate-path ${SAMPLE_FILE}"
    print_test_header "8" "Cross-Protocol Coordinate Mapper (NFS Mount -> Catalog Prefix -> S3 Key)" "$CMD"
    eval $CMD
    print_test_footer
else
    print_test_header "8" "Cross-Protocol Coordinate Mapper (SKIPPED — no sample file)" "N/A"
    echo -e "  ${YELLOW}Skipped: mount path unavailable or empty.${RESET}"
    print_test_footer
fi

# --- TEST 9: Multi-Protocol S3 Object Tag Mutation Lifecycle ---
if [ -n "$SAMPLE_FILE" ]; then
    CMD="${TOOL_EXEC} --add-s3-tag 'project=alpha_demo' --s3-target ${SAMPLE_FILE} && ${TOOL_EXEC} --modify-s3-tag 'project=beta_demo' --s3-target ${SAMPLE_FILE} && ${TOOL_EXEC} --delete-s3-tag 'project' --s3-target ${SAMPLE_FILE}"
    print_test_header "9" "S3 Protocol API Mutation Lifecycle (Put, Modify, Delete Object Tagging)" "$CMD"
    eval $CMD
    print_test_footer
else
    print_test_header "9" "S3 Protocol API Mutation Lifecycle (SKIPPED — no sample file)" "N/A"
    echo -e "  ${YELLOW}Skipped: resolve_sample_file found no active file under ${MOUNT_ROOT}.${RESET}"
    print_test_footer
fi

# --- TEST 10: Search Core - Early-Exit Client-Side Sparse Query ---
CMD="${TOOL_EXEC} --search --sparse --limit 5"
print_test_header "10" "Search Engine: Early-Exit Streamed Client Filter (Logical > Physical)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 11: Search Core - Chrono Time-Aging Constraints ---
CMD="${TOOL_EXEC} --search --ext locked --mmin 1440 --user vastdata --type file --limit 5"
print_test_header "11" "Search Engine: Multi-Dimensional Server-Side Pushdown Combination Query" "$CMD"
eval $CMD
print_test_footer

echo -e "${GREEN}========================================================================================${RESET}"
echo -e "                 ${BOLD_WHITE}ALL 11 EXTENDED DIAGNOSTIC AUDIT TASKS INITIALIZED SUCCESSFULY${RESET}"
echo -e "${GREEN}========================================================================================${RESET}"
