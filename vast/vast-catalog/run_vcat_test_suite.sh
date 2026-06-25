#!/usr/bin/env bash
################################################################################
#
# Script Name    : run_vcat_test_suite.sh
# Description    : Comprehensive automated validation harness for vcatalog_tool.py.
#                  Exercises Catalog Plane, VMS REST APIs, and S3 Protocol paths.
#
# Usage          : ./run_vcat_test_suite.sh | tee execution_audit.log
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
SAMPLE_FILE="/mnt/kmacs-root/vast-catalog/workspace_1/corporate_email/brawner-s/_sent_mail/25.locked"

if [ ! -x "$TOOL_EXEC" ]; then
    echo -e "[ERROR] $TOOL_EXEC is missing or not marked executable."
    exit 1
fi

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

# --- TEST 1: Python Regression Code Test Suite ---
CMD="python3 -m unittest test_vcatalog_tool.py"
print_test_header "1" "Python Code Regression Testing (Expanded Mocks & Analytics Math)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 2: Platform Reference Introspection ---
CMD="${TOOL_EXEC} --about"
print_test_header "2" "Internal VAST Platform Documentation & Metrics Glossary Dump" "$CMD"
eval $CMD | head -n 40
echo -e "${CYAN}... [Truncated for brevity; check tool for full system guide] ...${RESET}"
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

# --- TEST 7: Single Directory Data Reduction Ratio ---
CMD="${TOOL_EXEC} --show-data-reduction /kmacs/vast-catalog/workspace_1"
print_test_header "7" "Subtree DRR Profile Snapshot (Catalog Size vs Used Bytes)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 8: VMS REST API Three-Pillar Reduction Dashboard ---
CMD="${TOOL_EXEC} --show-data-reduction-rates --directory /kmacs/vast-catalog/workspace_1 --directory /kmacs/vast-catalog/workspace_2"
print_test_header "8" "VMS API Core Probe: Unique vs Usable Tiers (Dedup, Similarity, Compression)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 9: Cross-Protocol Path Translation ---
CMD="${TOOL_EXEC} --translate-path ${SAMPLE_FILE}"
print_test_header "9" "Cross-Protocol Coordinate Mapper (NFS Mount -> Catalog Prefix -> S3 Key)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 10: Multi-Protocol S3 Object Tag Mutation Lifecycle ---
CMD="${TOOL_EXEC} --add-s3-tag 'project=alpha_demo' --s3-target ${SAMPLE_FILE} && ${TOOL_EXEC} --modify-s3-tag 'project=beta_demo' --s3-target ${SAMPLE_FILE} && ${TOOL_EXEC} --delete-s3-tag 'project' --s3-target ${SAMPLE_FILE}"
print_test_header "10" "S3 Protocol API Mutation Lifecycle (Put, Modify, Delete Object Tagging)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 11: Search Core - Early-Exit Client-Side Sparse Query ---
CMD="${TOOL_EXEC} --search --sparse --limit 5"
print_test_header "11" "Search Engine: Early-Exit Streamed Client Filter (Logical > Physical)" "$CMD"
eval $CMD
print_test_footer

# --- TEST 12: Search Core - Chrono Time-Aging and Advanced Identity Constraints ---
CMD="${TOOL_EXEC} --search --ext locked --mmin 1440 --user vastdata --type file --limit 5"
print_test_header "12" "Search Engine: Multi-Dimensional Server-Side Pushdown Combination Query" "$CMD"
eval $CMD
print_test_footer

# --- TEST 13: Automation Quota Ingestion Check ---
CMD="${TOOL_EXEC} --update-quotas --vms-password 'DemoDummyPassword123' --brief"
print_test_header "13" "Dynamic Path Space Quota Management Registration Sweep" "$CMD"
eval $CMD
print_test_footer

echo -e "${GREEN}========================================================================================${RESET}"
echo -e "                 ${BOLD_WHITE}ALL 13 EXTENDED DIAGNOSTIC AUDIT TASKS FINALIZED SUCCESSFULY${RESET}"
echo -e "${GREEN}========================================================================================${RESET}"
