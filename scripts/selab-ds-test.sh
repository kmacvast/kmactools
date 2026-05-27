#!/bin/bash
################################################################################
# Script: selab-ds-test.sh
# Descr: Perform a VAST DataSpace consistency and failover validation test
#        across multiple mounted NFS exports participating in a GNS
#        relationship. Each loop writes a 10MB random payload file, forces
#        sync(), reads random 4KiB blocks from the opposite cluster for a
#        defined duration, writes a colored human-readable logfile entry,
#        and forces sync() again.
#
# Date: 2026-05-27
# Author: KMac
#
# Usage:
#
#    1/ Mount the target exports:
#
#       sudo mount -t nfs -o vers=3,tcp,nconnect=16 \
#           172.200.202.2:/kmacs/nfs-test-22 /mnt/var202
#
#       sudo mount -t nfs -o vers=3,tcp,nconnect=16 \
#           172.200.203.2:/kmacs/nfs-test-23 /mnt/var203
#
#    2/ Start the test:
#
#       bash ~/scripts/selab-ds-test.sh
#
#    3/ IMPORTANT:
#
#       Open a SECOND terminal window and tail the shared logfile:
#
#       tail -f /mnt/var203/dataspace/combined_output_log.txt
#
#       The script intentionally does NOT stream test output to stdout.
#       The logfile itself is the test artifact.
#
################################################################################

MAX_TIME_SECS=300
READ_DURATION_SECS=3
seconds=0
PAYLOAD_MB=10
BLOCK_SIZE_BYTES=4096
CLUSTERS=("var202" "var203")
OUTFILE="combined_output_log.txt"
PAYLOAD_FILE="gns_stress_payload.bin"

GREEN=$'\033[32m'
RED=$'\033[31m'
YELLOW=$'\033[33m'
CYAN=$'\033[36m'
RESET=$'\033[0m'

PAYLOAD_BYTES=$((PAYLOAD_MB * 1024 * 1024))
PAYLOAD_BLOCKS=$((PAYLOAD_BYTES / BLOCK_SIZE_BYTES))

opposite_cluster() {
    if [ "$1" = "var202" ]; then
        echo "var203"
    else
        echo "var202"
    fi
}

read_random_blocks() {
    READ_PATH="$1"
    END_TIME=$(($(date +%s) + READ_DURATION_SECS))
    READ_COUNT=0

    while [ "$(date +%s)" -lt "$END_TIME" ]; do
        BLOCK_OFFSET=$((RANDOM % PAYLOAD_BLOCKS))

        if dd if="${READ_PATH}" of=/dev/null bs="${BLOCK_SIZE_BYTES}" count=1 skip="${BLOCK_OFFSET}" status=none 2>/dev/null; then
            READ_COUNT=$((READ_COUNT + 1))
        else
            return 1
        fi
    done

    echo "${READ_COUNT}"
    return 0
}

echo
echo "=============================================================="
echo "      VAST GNS DATASPACE CONSISTENCY + LINK STRESS TEST"
echo "=============================================================="
echo
echo "THIS SCRIPT DOES NOT STREAM TEST OUTPUT TO STDOUT."
echo
echo
echo "OPEN A SECOND TERMINAL WINDOW NOW AND RUN:"
echo
echo "    tail -f /mnt/var203/dataspace/${OUTFILE}"
echo
echo
echo "Each cluster loop performs:"
echo "    10MB random payload write"
echo "    sync()"
echo "    ${READ_DURATION_SECS}s random 4KiB reads from the opposite cluster"
echo "    colored logfile write"
echo "    sync()"
echo
echo "=============================================================="
echo

for cluster in "${CLUSTERS[@]}"; do
    TARGET_DIR="/mnt/${cluster}/dataspace"

    if [ ! -d "$TARGET_DIR" ]; then
        echo "ERROR: Directory does not exist: $TARGET_DIR" >&2
        exit 1
    fi

    if [ ! -w "$TARGET_DIR" ]; then
        echo "ERROR: Cannot write to: $TARGET_DIR" >&2
        exit 1
    fi
done

echo "Mount validation successful."
echo "Pre-seeding payload files."
echo "Watch the SECOND terminal window for logfile output."
echo

for cluster in "${CLUSTERS[@]}"; do
    dd if=/dev/urandom of="/mnt/${cluster}/dataspace/${PAYLOAD_FILE}" bs=1M count="${PAYLOAD_MB}" status=none 2>/dev/null
    sync
done

while [ $seconds -lt $MAX_TIME_SECS ]
do
    for cluster in "${CLUSTERS[@]}"; do
        DTS=$(date +"%H:%M:%S.%6N")
        TARGET_DIR="/mnt/${cluster}/dataspace"
        LOG_PATH="${TARGET_DIR}/${OUTFILE}"
        PAYLOAD_PATH="${TARGET_DIR}/${PAYLOAD_FILE}"
        OTHER_CLUSTER=$(opposite_cluster "${cluster}")
        REMOTE_PAYLOAD_PATH="/mnt/${OTHER_CLUSTER}/dataspace/${PAYLOAD_FILE}"

        if dd if=/dev/urandom of="${PAYLOAD_PATH}" bs=1M count="${PAYLOAD_MB}" status=none 2>/dev/null; then
            if sync; then
                READ_COUNT=$(read_random_blocks "${REMOTE_PAYLOAD_PATH}")
                READ_RC=$?

                if [ "$READ_RC" -eq 0 ]; then
                    printf "%b\n" "${CYAN}${DTS}${RESET} | ${GREEN}${cluster}${RESET} | 10MB written, sync completed, read ${READ_COUNT} random 4KiB blocks from ${OTHER_CLUSTER}" >> "${LOG_PATH}" 2>/dev/null
                    sync
                else
                    printf "%b\n" "${CYAN}${DTS}${RESET} | ${YELLOW}${cluster}${RESET} | 10MB written, sync completed, remote random read warning from ${OTHER_CLUSTER}" >> "${LOG_PATH}" 2>/dev/null
                    sync
                fi
            else
                printf "%b\n" "${CYAN}${DTS}${RESET} | ${YELLOW}${cluster}${RESET} | 10MB written, payload sync warning" >> "${LOG_PATH}" 2>/dev/null
                sync
            fi
        else
            printf "%b\n" "${CYAN}${DTS}${RESET} | ${RED}${cluster}${RESET} | 10MB payload write failed" >> "${LOG_PATH}" 2>/dev/null
            sync
        fi
    done

    seconds=$((seconds + 1))
done

echo
echo "Test complete."
echo