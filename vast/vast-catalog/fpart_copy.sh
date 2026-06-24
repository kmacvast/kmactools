#!/bin/bash
# ==============================================================================
# SCRIPT NAME : vcat_seed_infinite.sh
# DESCRIPTION : Enterprise-grade, infinite data multiplication engine designed
#               to scale storage testing sandboxes indefinitely. Replaces finite
#               alpha loops with a dynamic Linux dictionary-word generator to
#               allow non-stop, overnight cluster saturation runs.
#
# AUTHOR      : KMac & Sheila
# DATE        : June 23, 2026
# VERSION     : 5.2.0
# LICENSE     : MIT / Enterprise Internal
#
# DEPENDENCIES: bash, fpart, ffp_sync, rsync, util-linux (setsid), coreutils (stdbuf)
#
# ==============================================================================
# REVISION HISTORY:
# Date       | Version | Author         | Summary of Changes
# -----------+---------+----------------+---------------------------------------
# 2026-06-23 | 5.2.0   | KMac & Sheila  | Added 'stdbuf -oL' line-buffering fix
#            |         |                | to force immediate log flush metrics.
# 2026-06-23 | 5.1.0   | KMac & Sheila  | Muted annoying tty warning noise via
#            |         |                | stderr process substitution filters.
# 2026-06-23 | 5.0.0   | KMac & Sheila  | Shifted from finite {d..z} loop to
#            |         |                | infinite random word generation loop.
# ==============================================================================
# USAGE EXAMPLES:
#   # Run as standard interactive engine (Hit Ctrl+C to terminate cleanly):
#   ./vcat_seed_infinite.sh
#
#   # Run as detached overnight background daemon:
#   nohup ./vcat_seed_infinite.sh > /tmp/fpart_multiplier.log 2>&1 &
#
# How to manually run fpsync with 32 parallel execution workers
# fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_1a/ /mnt/kmacs-root/vast-catalog/workspace_1c/
# ==============================================================================

# --- Path Configurations ---
MOUNT_ROOT="/mnt/kmacs-root/vast-catalog"
SRC_WS1="${MOUNT_ROOT}/workspace_1a"
SRC_WS2="${MOUNT_ROOT}/workspace_2a"
LOG_DIR="/tmp/fpart_copy_logs"
DICT_FILE="/usr/share/dict/words"

# --- Global Signal Trap ---
trap 'echo -e "\n[!] Interrupt Signal Captured! Terminating background operations..."; kill $pid_ws1 $pid_ws2 2>/dev/null; exit 0' SIGINT SIGTERM

# --- Phase 1: Pre-Flight Integrity Audits ---
echo "====================================================================="
echo " RUNTIME INTEGRITY CHECK"
echo "====================================================================="

if ! command -v fpsync &> /dev/null; then
    echo "[!] Error: 'fpsync' utility is not installed or missing from PATH."
    exit 1
fi

if [ ! -d "$MOUNT_ROOT" ]; then
    echo "[!] Error: Target VAST mount point missing or stale: $MOUNT_ROOT"
    exit 1
fi

if [ ! -d "$SRC_WS1" ] || [ ! -d "$SRC_WS2" ]; then
    echo "[!] Error: Core seed source layers missing!"
    exit 1
fi

mkdir -p "$LOG_DIR"
echo "[✓] Environment checked. Pre-flight checks passed."

# --- Phase 2: Infinite Dictionary-Driven Seeding Loop ---
echo -e "\n[*] Initialization complete. Entering non-stop multi-million file copy horizon."
echo "[*] Press [Ctrl+C] at any time to freeze pipelines and exit cleanly.\n"

while true; do
    # 1. Generate a clean, lowercase, alphanumeric random word
    if [ -f "$DICT_FILE" ]; then
        WORD=$(shuf -n 1 "$DICT_FILE" | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]')
    fi

    # Fallback safety boundary if dictionary file is missing from host OS
    if [ -z "$WORD" ]; then
        WORD="run_$(od -An -N2 -i /dev/urandom | awk '{print $1}')"
    fi

    DEST_WS1="${MOUNT_ROOT}/workspace_1_${WORD}"
    DEST_WS2="${MOUNT_ROOT}/workspace_2_${WORD}"

    # Idempotency Filter (Protects against rare random duplicate selections)
    if [ -d "$DEST_WS1" ] || [ -d "$DEST_WS2" ]; then
        continue
    fi

    echo "---------------------------------------------------------------------"
    echo " STARTING CONCURRENT WORD BLOCK: Target Suffix -> [_${WORD}]"
    echo "---------------------------------------------------------------------"

    LOG_WS1="${LOG_DIR}/fpsync_ws1_${WORD}.log"
    LOG_WS2="${LOG_DIR}/fpsync_ws2_${WORD}.log"

    :> "$LOG_WS1"
    :> "$LOG_WS2"

    # 2. Dispatch workers silently into terminal-detached sessions with output line-buffering forced
    setsid -w stdbuf -oL fpsync -n 32 -v "$SRC_WS1" "${DEST_WS1}/" > "$LOG_WS1" 2> >(grep -v "can't access tty" >> "$LOG_WS1") &
    pid_ws1=$!

    setsid -w stdbuf -oL fpsync -n 32 -v "$SRC_WS2" "${DEST_WS2}/" > "$LOG_WS2" 2> >(grep -v "can't access tty" >> "$LOG_WS2") &
    pid_ws2=$!

    echo "[+] Workers deployed. WS1 (PID: $pid_ws1) | WS2 (PID: $pid_ws2)"
    echo "[*] Tailoring active progress logs (polling intervals: 5s)..."

    # 3. Active Log Polling Telemetry Loop
    while kill -0 $pid_ws1 2>/dev/null || kill -0 $pid_ws2 2>/dev/null; do
        sleep 5

        STAT1=$(tail -n 15 "$LOG_WS1" | grep -E 'Parts done|Analyzing|crawling' | tail -n 1)
        STAT2=$(tail -n 15 "$LOG_WS2" | grep -E 'Parts done|Analyzing|crawling' | tail -n 1)

        STAT1_CLEAN=$(echo "$STAT1" | sed 's/^.*<=== //; s/^.*===> //')
        STAT2_CLEAN=$(echo "$STAT2" | sed 's/^.*<=== //; s/^.*===> //')

        echo "    [$(date +%T)] 1_${WORD}: ${STAT1_CLEAN:-Syncing...} | 2_${WORD}: ${STAT2_CLEAN:-Syncing...}"
    done

    # 4. Reclaim final exit states safely
    wait $pid_ws1; exit_ws1=$?
    wait $pid_ws2; exit_ws2=$?

    if [ $exit_ws1 -ne 0 ] || [ $exit_ws2 -ne 0 ]; then
        echo "[!] Warning: Word block '${WORD}' completed with network error tracking flags."
    else
        echo "[✓] Finished Word Block '${WORD}' successfully."
    fi
    echo ""
done
