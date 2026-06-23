#!/bin/bash
# ==============================================================================
# SCRIPT NAME : fpart_copy.sh
# DESCRIPTION : High-velocity, concurrent data multiplication engine designed
#               to scale storage testing sandboxes to tens of millions of files.
#               Leverages fpart directory splitting and fpsync backgrounding
#               (&) to orchestrate 64 simultaneous network execution streams,
#               fully saturating nconnect=16 NFS pipes straight to the VAST Data
#               distributed NVMe fabric.
#
# AUTHOR      : KMac & Sheila
# DATE        : June 23, 2026
# VERSION     : 3.1.0
# LICENSE     : MIT / Enterprise Internal
#
# DEPENDENCIES: bash, fpart, ffp_sync (part of fpart utility suite), rsync
# STORAGE ZONE: /mnt/kmacs-root/vast-catalog/
# ==============================================================================
# REVISION HISTORY:
# Date       | Version | Author         | Summary of Changes
# -----------+---------+----------------+---------------------------------------
# 2026-06-23 | 3.1.0   | KMac & Sheila  | Refactored to dual background jobs
#            |         |                | with PID tracking and 'wait' blocks
#            |         |                | for full concurrent execution.
# 2026-06-23 | 2.0.0   | KMac & Sheila  | Implemented alphabetical brace loops
#            |         |                | ({d..z}) for automated alpha expansion.
# 2026-06-23 | 1.0.0   | KMac & Sheila  | Initial sequential workspace_1b copy.
# ==============================================================================
# USAGE EXAMPLES:
#   # Run as standard utility (Ensure mount is active prior to launch):
#   ./fpart_copy.sh
#
#   # Run and decouple from active terminal shell (Great for long alphabet runs):
#   nohup ./fpart_copy.sh > /tmp/fpart_multiplier.log 2>&1 &
#
# How to manually run fpsync with 32 parallel execution workers
# fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_1a/ /mnt/kmacs-root/vast-catalog/workspace_1c/
# fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_2a/ /mnt/kmacs-root/vast-catalog/workspace_2c/
#
# ==============================================================================

# --- Path Configurations ---
MOUNT_ROOT="/mnt/kmacs-root/vast-catalog"
SRC_WS1="${MOUNT_ROOT}/workspace_1a"
SRC_WS2="${MOUNT_ROOT}/workspace_2a"
LOG_DIR="./logs"

# --- Global Signal Trap ---
# Ensures hitting Ctrl+C cleanly terminates background workers instead of leaving orphans
trap 'echo -e "\n[!] Interrupt Signal Captured! Killing active background engines..."; kill $pid_ws1 $pid_ws2 2>/dev/null; exit 1' SIGINT SIGTERM

# --- Phase 1: Pre-Flight Integrity Audits ---
echo "====================================================================="
echo " RUNTIME INTEGRITY CHECK"
echo "====================================================================="

# 1. Verify binary availability
if ! command -v fpsync &> /dev/null; then
    echo "[!] Error: 'fpsync' utility is not installed or missing from PATH."
    exit 1
fi

# 2. Verify active mount framework accessibility
if [ ! -d "$MOUNT_ROOT" ]; then
    echo "[!] Error: Target VAST mount point missing or stale: $MOUNT_ROOT"
    exit 1
fi

# 3. Validate presence of core seed layer sources
if [ ! -d "$SRC_WS1" ] || [ ! -d "$SRC_WS2" ]; then
    echo "[!] Error: Core seed source layers missing!"
    echo "    Looking for: $SRC_WS1"
    echo "    Looking for: $SRC_WS2"
    exit 1
fi

# 4. Ensure runtime log directories exist
mkdir -p "$LOG_DIR"
echo "[✓] Environment checked. Pre-flight checks passed."

# --- Phase 2: Concurrent Alpha Multiplication Loop ---
for char in {d..z}; do
    echo "---------------------------------------------------------------------"
    echo " STARTING CONCURRENT ALPHA BLOCK: Workspace 1${char} & 2${char}"
    echo "---------------------------------------------------------------------"

    DEST_WS1="${MOUNT_ROOT}/workspace_1${char}/"
    DEST_WS2="${MOUNT_ROOT}/workspace_2${char}/"
    LOG_WS1="${LOG_DIR}/fpsync_ws1${char}.log"
    LOG_WS2="${LOG_DIR}/fpsync_ws2${char}.log"

    # 1. Fire Workspace 1 Copy - Detach stdin (</dev/null) to prevent terminal freezing
    fpsync -n 32 -v "$SRC_WS1" "$DEST_WS1" < /dev/null > "$LOG_WS1" 2>&1 &
    pid_ws1=$!
    echo "[+] Launched Workspace 1${char} Stream (PID: $pid_ws1) -> Log: $LOG_WS1"

    # 2. Fire Workspace 2 Copy - Detach stdin (</dev/null) to prevent terminal freezing
    fpsync -n 32 -v "$SRC_WS2" "$DEST_WS2" < /dev/null > "$LOG_WS2" 2>&1 &
    pid_ws2=$!
    echo "[+] Launched Workspace 2${char} Stream (PID: $pid_ws2) -> Log: $LOG_WS2"

    echo "[*] Synchronizing parallel threads... Processing 64 cluster operations."

    # 3. Wait securely for both active transfers to finish before shifting letters
    wait $pid_ws1
    exit_ws1=$?

    wait $pid_ws2
    exit_ws2=$?

    # 4. Audit execution return status codes
    if [ $exit_ws1 -ne 0 ] || [ $exit_ws2 -ne 0 ]; then
        echo "[!] Warning: Alpha block '${char}' finished with errors."
        echo "    WS1 Exit Code: $exit_ws1 | WS2 Exit Code: $exit_ws2"
        echo "    Inspect files inside $LOG_DIR for specific network error traces."
    else
        echo "[✓] Finished Alpha Block '${char}' successfully."
    fi
    echo ""
done

echo "====================================================================="
echo " SUCCESS: Full 30+ Million File Matrix Seeding Complete!"
echo "====================================================================="
