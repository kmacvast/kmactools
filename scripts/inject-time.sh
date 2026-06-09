#!/bin/bash
################################################################################
# Script: inject-time.sh
#
# Descr : Benchmark utility used to quantify the effects of injected network
#         latency on Global Synced DataSpace NFS exports, including sequential
#         read/write performance and metadata operation latency.
#
# Usage:
#
#   ./inject-time.sh -m <mount_profile> -l <latency>
#
################################################################################

set -euo pipefail

MOUNT_ID=""
LATENCY=""

# Internal operational properties
IS_LOCAL=false
NFS_SERVER=""
NFS_EXPORT=""
NFS_SERVER_SHARE=""
NFS_OPTIONS=""
MOUNT_TARGET=""
LOCAL_DEVICE=""

CONFIG_FILE="${HOME}/.inject_latency.conf"
LOGS_DIR="./logs"

SCRIPT_EXIT_CODE=0

# =========================================================================
# UTILITY FUNCTIONS
# =========================================================================

log() {
    local level="$1"
    local msg="$2"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [${level}] ${msg}" >&2
}

die() {
    log "ERROR" "$1"
    exit 1
}

usage() {
    echo "Usage: $0 -m <mount_profile> -l <latency>" >&2
    echo "  -m  Required. Profile identifier exactly matching:" >&2
    echo "                 -> dataspace-origin" >&2
    echo "                 -> dataspace-satellite" >&2
    echo "                 -> no-dataspace" >&2
    echo "  -l  Required: Injected latency profile (e.g., baseline, 50ms)" >&2
    echo "  -h  Show this help message" >&2
    exit 1
}

# Cross-platform sub-second timestamp (macOS date lacks %N)
get_timestamp() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c "import time; print('%.9f' % time.time())"
    elif date +%s.%N 2>/dev/null | grep -qv '%N'; then
        date +%s.%N
    else
        date +%s
    fi
}

elapsed_seconds() {
    local start="$1" end="$2"
    awk "BEGIN { printf \"%.3f\", $end - $start }"
}

# =========================================================================
# PREREQUISITE VALIDATION
# =========================================================================

validate_prerequisites() {
    local missing=()

    command -v fio    >/dev/null 2>&1 || missing+=("fio")
    command -v sudo   >/dev/null 2>&1 || missing+=("sudo")
    command -v mount  >/dev/null 2>&1 || missing+=("mount")
    command -v umount >/dev/null 2>&1 || missing+=("umount")

    if [ ${#missing[@]} -gt 0 ]; then
        die "Missing required tools: ${missing[*]}. Install them before running this script."
    fi

    if ! command -v jq >/dev/null 2>&1; then
        log "WARN" "jq is not installed. Metric extraction will use grep fallback (less reliable)."
    fi

    # Verify sudo access without a password for the operations we need
    if ! sudo -n true 2>/dev/null; then
        die "This script requires passwordless sudo. Configure /etc/sudoers or run: sudo -v first."
    fi
}

# =========================================================================
# CONFIGURATION FILE VALIDATION
# =========================================================================

validate_config_file() {
    if [ ! -e "${CONFIG_FILE}" ]; then
        die "Configuration file not found: ${CONFIG_FILE}
  Create it with one pipe-delimited entry per line:
    <server_ip>|<export_path>|<mount_options>|<local_mountpoint>
  For local block devices use LOCAL as the server:
    LOCAL|<device_path>|<mount_options>|<local_mountpoint>"
    fi

    if [ ! -f "${CONFIG_FILE}" ]; then
        die "Configuration path exists but is not a regular file: ${CONFIG_FILE}"
    fi

    if [ ! -r "${CONFIG_FILE}" ]; then
        die "Configuration file is not readable (check permissions): ${CONFIG_FILE}"
    fi

    if [ ! -s "${CONFIG_FILE}" ]; then
        die "Configuration file is empty: ${CONFIG_FILE}"
    fi

    # Check that at least one non-comment, non-blank line exists with 4 pipe-delimited fields
    local valid_line_count
    valid_line_count=$(grep -cv '^\s*\(#\|$\)' "${CONFIG_FILE}" 2>/dev/null || echo 0)
    if [ "${valid_line_count}" -eq 0 ]; then
        die "Configuration file contains no valid entries (only comments/blank lines): ${CONFIG_FILE}"
    fi

    local malformed_lines
    malformed_lines=$(grep -v '^\s*\(#\|$\)' "${CONFIG_FILE}" | awk -F'|' 'NF != 4 { print NR": "$0 }')
    if [ -n "${malformed_lines}" ]; then
        die "Malformed lines in ${CONFIG_FILE} (expected exactly 4 pipe-delimited fields):
${malformed_lines}"
    fi
}

# =========================================================================
# CONFIGURATION PARSING
# =========================================================================

parse_config() {
    local found=false

    while IFS='|' read -r cfg_server cfg_export cfg_options cfg_mountpoint || [ -n "$cfg_server" ]; do
        cfg_server=$(echo "${cfg_server}"    | xargs 2>/dev/null || echo "${cfg_server}")
        cfg_export=$(echo "${cfg_export}"    | xargs 2>/dev/null || echo "${cfg_export}")
        cfg_options=$(echo "${cfg_options}"  | xargs 2>/dev/null || echo "${cfg_options}")
        cfg_mountpoint=$(echo "${cfg_mountpoint}" | xargs 2>/dev/null || echo "${cfg_mountpoint}")

        [[ -z "${cfg_server}" || "${cfg_server}" =~ ^# ]] && continue

        if [[ "${cfg_mountpoint}" == *"${MOUNT_ID}" ]]; then
            # Validate that no required field is empty
            [ -z "${cfg_server}"     ] && die "Config entry matched [${MOUNT_ID}] but has an empty server field."
            [ -z "${cfg_export}"     ] && die "Config entry matched [${MOUNT_ID}] but has an empty export/device field."
            [ -z "${cfg_options}"    ] && die "Config entry matched [${MOUNT_ID}] but has an empty options field."
            [ -z "${cfg_mountpoint}" ] && die "Config entry matched [${MOUNT_ID}] but has an empty mountpoint field."

            MOUNT_TARGET="${cfg_mountpoint}"
            NFS_OPTIONS="${cfg_options}"

            if [ "${cfg_server}" = "LOCAL" ]; then
                IS_LOCAL=true
                LOCAL_DEVICE="${cfg_export}"
            else
                IS_LOCAL=false
                NFS_SERVER="${cfg_server}"
                NFS_EXPORT="${cfg_export}"
                NFS_SERVER_SHARE="${cfg_server}:${cfg_export}"
            fi
            found=true
            break
        fi
    done < "${CONFIG_FILE}"

    if [ "${found}" = false ]; then
        die "No entry matching profile [${MOUNT_ID}] found in ${CONFIG_FILE}.
  Ensure the mountpoint field of an entry ends with '${MOUNT_ID}'."
    fi
}

# =========================================================================
# RESOURCE REACHABILITY VALIDATION
# =========================================================================

validate_resources() {
    log "INFO" "Validating configuration resources for profile [${MOUNT_ID}]..."

    # Validate local mount target directory
    if [ ! -e "${MOUNT_TARGET}" ]; then
        die "Mount target directory does not exist: ${MOUNT_TARGET}
  Create it with: sudo mkdir -p ${MOUNT_TARGET}"
    fi
    if [ ! -d "${MOUNT_TARGET}" ]; then
        die "Mount target path exists but is not a directory: ${MOUNT_TARGET}"
    fi

    if [ "${IS_LOCAL}" = true ]; then
        # Validate local block device
        if [ ! -e "${LOCAL_DEVICE}" ]; then
            die "Local block device does not exist: ${LOCAL_DEVICE}"
        fi
        if [ ! -b "${LOCAL_DEVICE}" ]; then
            die "Local device path exists but is not a block device: ${LOCAL_DEVICE}"
        fi
    else
        # Validate NFS server IP/hostname format (basic sanity, not strict)
        if [[ ! "${NFS_SERVER}" =~ ^[a-zA-Z0-9._-]+$ ]]; then
            die "NFS server address appears malformed: '${NFS_SERVER}'"
        fi

        # Validate NFS export path starts with /
        if [[ ! "${NFS_EXPORT}" =~ ^/ ]]; then
            die "NFS export path must be an absolute path (start with /): '${NFS_EXPORT}'"
        fi

        # Check NFS server is reachable on port 2049
        log "INFO" "Checking NFS server reachability: ${NFS_SERVER}:2049..."
        if command -v nc >/dev/null 2>&1; then
            if ! nc -z -w 5 "${NFS_SERVER}" 2049 2>/dev/null; then
                die "NFS server is not reachable on port 2049: ${NFS_SERVER}
  Check network connectivity, firewall rules, and that the NFS service is running."
            fi
        elif command -v bash >/dev/null 2>&1; then
            if ! (echo >/dev/tcp/"${NFS_SERVER}"/2049) 2>/dev/null; then
                die "NFS server is not reachable on port 2049: ${NFS_SERVER}
  Check network connectivity, firewall rules, and that the NFS service is running."
            fi
        else
            log "WARN" "Cannot verify NFS server reachability (nc not available). Proceeding..."
        fi
        log "INFO" "NFS server ${NFS_SERVER} is reachable on port 2049."
    fi

    # Validate mount options are non-trivially set
    if [ -z "${NFS_OPTIONS}" ]; then
        die "Mount options field is empty for profile [${MOUNT_ID}]. Expected options like 'vers=3,tcp'."
    fi

    # Validate logs directory is writable (or creatable)
    mkdir -p "${LOGS_DIR}" 2>/dev/null || die "Cannot create logs directory: ${LOGS_DIR}"
    if [ ! -w "${LOGS_DIR}" ]; then
        die "Logs directory is not writable: ${LOGS_DIR}"
    fi

    log "INFO" "All resource validation checks passed."
}

# =========================================================================
# MOUNT MANAGEMENT
# =========================================================================

remount_and_drop_caches() {
    local mnt="${MOUNT_TARGET}"

    log "INFO" "Cleaning up processes using ${mnt}..."
    sudo fuser -ku "${mnt}" 2>/dev/null || true

    log "INFO" "Unmounting ${mnt}..."
    sudo umount "${mnt}" 2>/dev/null || true

    log "INFO" "Dropping system memory caches (PageCache, dentries, inodes)..."
    echo 3 | sudo tee /proc/sys/vm/drop_caches > /dev/null

    if [ "${IS_LOCAL}" = true ]; then
        log "INFO" "Mounting local block device ${LOCAL_DEVICE} to ${mnt}..."
        sudo mount -o "${NFS_OPTIONS}" "${LOCAL_DEVICE}" "${mnt}"
    else
        log "INFO" "Mounting NFS share [${NFS_SERVER_SHARE}] to ${mnt} with options [${NFS_OPTIONS}]..."
        sudo mount -t nfs -o "${NFS_OPTIONS}" "${NFS_SERVER_SHARE}" "${mnt}"
    fi

    if [ $? -ne 0 ]; then
        die "Failed to mount ${mnt}."
    fi
    log "INFO" "Successfully mounted ${mnt}."

    log "INFO" "Ensuring write permissions for user $(id -un) on ${mnt}/test1..."
    sudo mkdir -p "${mnt}/test1"
    sudo chown "$(id -u):$(id -g)" "${mnt}/test1"
}

# =========================================================================
# FIO TEST RUNNER
# =========================================================================

run_fio_test() {
    local mode="$1"
    local filepath="$2"   # Full path to the test file (directory + filename)
    local logfile="$3"

    log "INFO" "Starting FIO ${mode} benchmark..."

    fio --name="seq${mode}" \
        --filename="${filepath}" \
        --rw="${mode}" \
        --bs=1M \
        --size=10G \
        --numjobs=1 \
        --iodepth=32 \
        --direct=1 \
        --time_based=0 \
        --output-format=json > "${logfile}" 2>/dev/null

    local rc=$?
    if [ ${rc} -ne 0 ]; then
        die "FIO ${mode} test exited with code ${rc}. Check ${logfile} for details."
    fi

    if [ ! -s "${logfile}" ]; then
        die "FIO ${mode} produced an empty output file: ${logfile}
  This usually means FIO crashed or could not access the test file."
    fi

    # FIO >= 3.x writes informational text (e.g. "note: iodepth capped...") to
    # stdout before the JSON block. Strip any leading non-JSON lines so that jq
    # can parse the file without errors.
    local tmpfile="${logfile}.strip"
    awk '/^\{/{found=1} found{print}' "${logfile}" > "${tmpfile}" \
        && mv "${tmpfile}" "${logfile}" \
        || rm -f "${tmpfile}"
}

# =========================================================================
# METRIC EXTRACTION
# =========================================================================

# Returns bandwidth in MB/s for the given job type (read|write).
# FIO JSON: .bw is KiB/s (all versions); .bw_bytes is bytes/s (FIO >= 3.1).
# Prefer bw_bytes; fall back to bw*1024 bytes → /1024/1024 = bw/1024 MB/s.
extract_bw_mbs() {
    local json_file="$1"
    local job_type="$2"

    if command -v jq >/dev/null 2>&1; then
        local raw_val
        raw_val=$(jq -r --arg jt "$job_type" '
            .jobs[0][$jt] |
            if .bw_bytes != null and (.bw_bytes | tonumber) > 0 then
                (.bw_bytes / 1048576)
            elif .bw != null and (.bw | tonumber) > 0 then
                (.bw / 1024)
            else
                0
            end
        ' "${json_file}" 2>/dev/null) || raw_val=""
        if [ -n "${raw_val}" ] && [ "${raw_val}" != "null" ]; then
            LC_ALL=C printf "%.2f\n" "${raw_val}"
        else
            echo "0.00"
        fi
    else
        # Fallback: grep for bw_bytes first, then bw
        local raw
        raw=$(grep -oP '"bw_bytes"\s*:\s*\K[0-9]+' "${json_file}" 2>/dev/null | head -n1)
        if [ -n "${raw}" ] && [ "${raw}" -gt 0 ] 2>/dev/null; then
            awk "BEGIN { printf \"%.2f\", ${raw} / 1048576 }"
        else
            raw=$(grep -oP '"bw"\s*:\s*\K[0-9]+' "${json_file}" 2>/dev/null | head -n1)
            if [ -n "${raw}" ] && [ "${raw}" -gt 0 ] 2>/dev/null; then
                awk "BEGIN { printf \"%.2f\", ${raw} / 1024 }"
            else
                echo "0.00"
            fi
        fi
    fi
}

# Returns IOPS (integer) for the given job type.
extract_iops() {
    local json_file="$1"
    local job_type="$2"

    if command -v jq >/dev/null 2>&1; then
        local raw_val
        raw_val=$(jq -r --arg jt "$job_type" '.jobs[0][$jt].iops // 0 | floor' \
            "${json_file}" 2>/dev/null) || raw_val=""
        if [ -n "${raw_val}" ] && [ "${raw_val}" != "null" ]; then
            printf "%d\n" "${raw_val}" 2>/dev/null || echo "0"
        else
            echo "0"
        fi
    else
        grep -oP '"iops"\s*:\s*\K[0-9.]+' "${json_file}" 2>/dev/null \
            | head -n1 | cut -d. -f1 || echo "0"
    fi
}

# Returns io_bytes for the given job type (for completeness validation).
extract_io_bytes() {
    local json_file="$1"
    local job_type="$2"

    if command -v jq >/dev/null 2>&1; then
        jq -r --arg jt "$job_type" '.jobs[0][$jt].io_bytes // 0 | tostring' \
            "${json_file}" 2>/dev/null || echo "0"
    else
        grep -oP '"io_bytes"\s*:\s*\K[0-9]+' "${json_file}" 2>/dev/null | head -n1 || echo "0"
    fi
}

# =========================================================================
# RESULT VALIDATION
# =========================================================================

# Validates that a benchmark JSON produced meaningful, non-zero results.
# Arguments: json_file  job_type  phase_label  min_bw_mbs
validate_fio_result() {
    local json_file="$1"
    local job_type="$2"
    local phase_label="$3"
    local min_bw_mbs="${4:-1}"    # Minimum acceptable bandwidth in MB/s

    local errors=()

    if [ ! -f "${json_file}" ]; then
        errors+=("Output file does not exist: ${json_file}")
    elif [ ! -s "${json_file}" ]; then
        errors+=("Output file is empty: ${json_file}")
    else
        # Structural check: must be valid JSON with a jobs array
        if command -v jq >/dev/null 2>&1; then
            if ! jq -e '.jobs | length > 0' "${json_file}" >/dev/null 2>&1; then
                errors+=("Output JSON is missing or has an empty 'jobs' array.")
            else
                local bw_bytes io_bytes iops error_count
                bw_bytes=$(jq -r --arg jt "$job_type" '.jobs[0][$jt].bw_bytes // 0' "${json_file}" 2>/dev/null || echo "0")
                bw_kib=$(jq -r --arg jt "$job_type" '.jobs[0][$jt].bw // 0' "${json_file}" 2>/dev/null || echo "0")
                io_bytes=$(jq -r --arg jt "$job_type" '.jobs[0][$jt].io_bytes // 0' "${json_file}" 2>/dev/null || echo "0")
                iops=$(jq -r --arg jt "$job_type" '.jobs[0][$jt].iops // 0' "${json_file}" 2>/dev/null || echo "0")
                error_count=$(jq -r '.jobs[0].error // 0' "${json_file}" 2>/dev/null || echo "0")

                # Bandwidth check (accept either bw_bytes or bw KiB/s)
                local effective_bw_mbs
                effective_bw_mbs=$(awk "BEGIN {
                    b = $bw_bytes + 0; k = $bw_kib + 0;
                    if (b > 0) printf \"%.2f\", b/1048576;
                    else printf \"%.2f\", k/1024
                }")
                if awk "BEGIN { exit ($effective_bw_mbs >= $min_bw_mbs) ? 0 : 1 }"; then
                    : # OK
                else
                    errors+=("Bandwidth is ${effective_bw_mbs} MB/s, below minimum threshold of ${min_bw_mbs} MB/s. I/O may not have executed.")
                fi

                # io_bytes: for a 10G test expect >= 10737418240 bytes
                local expected_io=10737418240
                if [ "$(awk "BEGIN { print ($io_bytes >= $expected_io) ? 1 : 0 }")" != "1" ]; then
                    local actual_gib
                    actual_gib=$(awk "BEGIN { printf \"%.2f\", $io_bytes / 1073741824 }")
                    errors+=("Only ${actual_gib} GiB of I/O recorded (expected 10 GiB). Test may have been truncated or skipped.")
                fi

                # FIO-reported job error
                if [ "${error_count}" != "0" ] && [ "${error_count}" != "null" ]; then
                    errors+=("FIO reported a job error code: ${error_count}")
                fi
            fi
        else
            # No jq: minimal grep-based sanity check
            if ! grep -q '"jobs"' "${json_file}"; then
                errors+=("Output file does not look like FIO JSON (missing 'jobs' key).")
            fi
            local raw_bw
            raw_bw=$(grep -oP '"bw_bytes"\s*:\s*\K[0-9]+' "${json_file}" 2>/dev/null | head -n1)
            [ -z "${raw_bw}" ] && raw_bw=$(grep -oP '"bw"\s*:\s*\K[0-9]+' "${json_file}" 2>/dev/null | head -n1)
            if [ -z "${raw_bw}" ] || [ "${raw_bw}" -eq 0 ] 2>/dev/null; then
                errors+=("Could not extract a non-zero bandwidth value from output JSON.")
            fi
        fi
    fi

    if [ ${#errors[@]} -gt 0 ]; then
        log "ERROR" "=== ${phase_label} RESULT VALIDATION FAILED ==="
        for err in "${errors[@]}"; do
            log "ERROR" "  • ${err}"
        done
        log "ERROR" "The benchmark did not execute correctly. Raw output: ${json_file}"
        SCRIPT_EXIT_CODE=1
    fi
}

# =========================================================================
# ARGUMENT PARSING
# =========================================================================

while getopts "m:l:h" opt; do
    case "${opt}" in
        m) MOUNT_ID="${OPTARG}" ;;
        l) LATENCY="${OPTARG}" ;;
        h) usage ;;
        *) usage ;;
    esac
done

if [[ "${MOUNT_ID}" != "dataspace-origin" && \
      "${MOUNT_ID}" != "dataspace-satellite" && \
      "${MOUNT_ID}" != "no-dataspace" ]]; then
    log "ERROR" "Invalid or missing mount profile. Must be exactly: dataspace-origin, dataspace-satellite, or no-dataspace."
    usage
fi

if [ -z "${LATENCY}" ]; then
    log "ERROR" "Missing mandatory parameter: -l <latency> is required."
    usage
fi

# =========================================================================
# STARTUP CHECKS
# =========================================================================

validate_prerequisites
validate_config_file
parse_config
validate_resources

# =========================================================================
# TEST FILE AND LOG PATHS
# =========================================================================

RUN_TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
WRITE_LOG="${LOGS_DIR}/fio_${MOUNT_ID}_${LATENCY}_${RUN_TIMESTAMP}_write.json"
READ_LOG="${LOGS_DIR}/fio_${MOUNT_ID}_${LATENCY}_${RUN_TIMESTAMP}_read.json"

# Full path to test file; using --filename (not --directory + --filename)
# avoids FIO path-joining ambiguity across versions.
TEST_FILE="${MOUNT_TARGET}/test1/${MOUNT_ID}-${RANDOM}.rnd"

# =========================================================================
# PHASE 1: WRITE
# =========================================================================

log "INFO" "Executing Phase 1 (Write Performance)..."
START_TIME=$(get_timestamp)
remount_and_drop_caches
run_fio_test "write" "${TEST_FILE}" "${WRITE_LOG}"
END_TIME=$(get_timestamp)
WRITE_PHASE_TIME=$(elapsed_seconds "$START_TIME" "$END_TIME")

# =========================================================================
# PHASE 2: READ
# =========================================================================

log "INFO" "Executing Phase 2 (Read Performance)..."
START_TIME=$(get_timestamp)
remount_and_drop_caches
run_fio_test "read" "${TEST_FILE}" "${READ_LOG}"
END_TIME=$(get_timestamp)
READ_PHASE_TIME=$(elapsed_seconds "$START_TIME" "$END_TIME")

# =========================================================================
# PHASE 3: METADATA (DIRECTORY LISTING)
# =========================================================================

log "INFO" "Executing Phase 3 (Metadata Performance)..."
remount_and_drop_caches
sudo mkdir -p "${MOUNT_TARGET}/test1/subdirectory"
sudo chown "$(id -u):$(id -g)" "${MOUNT_TARGET}/test1/subdirectory"
LIST_DIR="${MOUNT_TARGET}/test1/subdirectory/"

log "INFO" "Timing directory listing for ${LIST_DIR}..."
START_TIME=$(get_timestamp)
ls "${LIST_DIR}" > /dev/null
END_TIME=$(get_timestamp)
METADATA_TIME=$(elapsed_seconds "$START_TIME" "$END_TIME")

log "INFO" "All benchmark I/O operations completed."

# =========================================================================
# RESULT EXTRACTION & VALIDATION
# =========================================================================

validate_fio_result "${WRITE_LOG}" "write" "Phase 1 Write" 1
validate_fio_result "${READ_LOG}"  "read"  "Phase 2 Read"  1

WRITE_BW=$(extract_bw_mbs   "${WRITE_LOG}" "write")
WRITE_IOPS=$(extract_iops   "${WRITE_LOG}" "write")
READ_BW=$(extract_bw_mbs    "${READ_LOG}"  "read")
READ_IOPS=$(extract_iops    "${READ_LOG}"  "read")

[[ -z "${WRITE_BW}"   ]] && WRITE_BW="0.00"
[[ -z "${WRITE_IOPS}" ]] && WRITE_IOPS="0"
[[ -z "${READ_BW}"    ]] && READ_BW="0.00"
[[ -z "${READ_IOPS}"  ]] && READ_IOPS="0"

# =========================================================================
# SUMMARY REPORT
# =========================================================================

echo ""
echo "========================================================================="
echo "                   BENCHMARK RUN SUMMARY REPORT                          "
echo "========================================================================="
printf "%-25s : %s\n" "Execution Date"          "$(date +'%Y-%m-%d %H:%M:%S')"
printf "%-25s : %s\n" "Target Mount ID"         "${MOUNT_ID}"
printf "%-25s : %s\n" "Mount Path"              "${MOUNT_TARGET}"
printf "%-25s : %s\n" "Injected Latency Profile" "${LATENCY}"
echo "-------------------------------------------------------------------------"
echo " METRIC                  | PERFORMANCE VALUE"
echo "-------------------------------------------------------------------------"
printf " %-23s | %s MB/s\n"  "Sequential Write BW"    "${WRITE_BW}"
printf " %-23s | %s IOPS\n"  "Sequential Write IOPS"  "${WRITE_IOPS}"
printf " %-23s | %s MB/s\n"  "Sequential Read BW"     "${READ_BW}"
printf " %-23s | %s IOPS\n"  "Sequential Read IOPS"   "${READ_IOPS}"
echo "-------------------------------------------------------------------------"
echo " PHASE ELAPSED TIMING    | RUNTIME DURATION"
echo "-------------------------------------------------------------------------"
printf " %-23s | %s seconds\n" "Phase 1: Write Total"   "${WRITE_PHASE_TIME}"
printf " %-23s | %s seconds\n" "Phase 2: Read Total"    "${READ_PHASE_TIME}"
printf " %-23s | %s seconds\n" "Phase 3: Metadata Total" "${METADATA_TIME}"
echo "-------------------------------------------------------------------------"
echo "Raw Outputs Saved Inside Local Directory:"
echo "  [Write JSON]: ${WRITE_LOG}"
echo "  [Read JSON] : ${READ_LOG}"
echo "========================================================================="
echo ""

if [ "${SCRIPT_EXIT_CODE}" -ne 0 ]; then
    log "ERROR" "One or more benchmark result validations failed. Review errors above before treating this run as valid."
fi

exit "${SCRIPT_EXIT_CODE}"

