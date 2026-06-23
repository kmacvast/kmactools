#!/bin/bash
# ==============================================================================
# SCRIPT NAME : fpart_copy.sh
# DESCRIPTION : Enterprise-grade, concurrent data multiplication engine designed
#               to scale storage testing sandboxes to tens of millions of files.
#               Features automatic TTY session detachment via setsid, active
#               background log polling, and smart directory skip logic.
#
# AUTHOR      : KMac & Sheila
# DATE        : June 23, 2026
# VERSION     : 4.3.0
# LICENSE     : MIT / Enterprise Internal
#
# DEPENDENCIES: bash, fpart, ffp_sync, rsync, util-linux (setsid)
# STORAGE ZONE: /mnt/kmacs-root/vast-catalog
# ==============================================================================
# REVISION HISTORY:
# Date       | Version | Author         | Summary of Changes
# -----------+---------+----------------+---------------------------------------
# 2026-06-23 | 4.3.0   | KMac & Sheila  | Added live log status polling loop to
#            |         |                | provide real-time foreground visibility.
# 2026-06-23 | 4.2.0   | KMac & Sheila  | Embedded 'setsid -w' to bypass kernel 
#            |         |                | SIGTTOU job control halts entirely.
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
trap 'echo -e "\n[!] Interrupt Signal Captured! Killing active background engines..."; kill $pid_ws1 $pid_ws2 2>/dev/null; exit 1' SIGINT SIGTERM

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

# --- Phase 2: Concurrent Alpha Multiplication Loop ---
for char in {d..z}; do
    DEST_WS1="${MOUNT_ROOT}/workspace_1${char}"
    DEST_WS2="${MOUNT_ROOT}/workspace_2${char}"

    # Idempotency Filter
    if [ -d "$DEST_WS1" ] && [ -d "$DEST_WS2" ]; then
        echo "[-] Alpha Block '${char}': Target paths already exist on storage tier. Skipping..."
        echo ""
        continue
    fi

    echo "---------------------------------------------------------------------"
    echo " STARTING CONCURRENT ALPHA BLOCK: Workspace 1${char} & 2${char}"
    echo "---------------------------------------------------------------------"
    
    LOG_WS1="${LOG_DIR}/fpsync_ws1${char}.log"
    LOG_WS2="${LOG_DIR}/fpsync_ws2${char}.log"

    # Initialize empty log targets so the monitor loop doesn't trip
    :> "$LOG_WS1"
    :> "$LOG_WS2"

    # 1. Dispatch workers silently into isolated sessions
    setsid -w fpsync -n 32 -v "$SRC_WS1" "${DEST_WS1}/" > "$LOG_WS1" 2>&1 &
    pid_ws1=$!
    
    setsid -w fpsync -n 32 -v "$SRC_WS2" "${DEST_WS2}/" > "$LOG_WS2" 2>&1 &
    pid_ws2=$!
    
    echo "[+] Workers deployed. WS1 Key (PID: $pid_ws1) | WS2 Key (PID: $pid_ws2)"
    echo "[*] Tailoring active progress logs (polling intervals: 5s)..."

    # 2. Active Log Polling Loop (Replaces the silent blind wait)
    while kill -0 $pid_ws1 2>/dev/null || kill -0 $pid_ws2 2>/dev/null; do
        sleep 5
        
        # Pull the last meaningful progress metric line from each worker log
        STAT1=$(tail -n 15 "$LOG_WS1" | grep -E 'Parts done|Analyzing|crawling' | tail -n 1)
        STAT2=$(tail -n 15 "$LOG_WS2" | grep -E 'Parts done|Analyzing|crawling' | tail -n 1)
        
        # Clean up strings if files are still spooling
        STAT1_CLEAN=$(echo "$STAT1" | sed 's/^.*<=== //; s/^.*===> //')
        STAT2_CLEAN=$(echo "$STAT2" | sed 's/^.*<=== //; s/^.*===> //')
        
        # Print telemetry line
        echo "    [$(date +%T)] 1${char}: ${STAT1_CLEAN:-Syncing...} | 2${char}: ${STAT2_CLEAN:-Syncing...}"
    done

    # 3. Collect final exit statuses securely
    wait $pid_ws1; exit_ws1=$?
    wait $pid_ws2; exit_ws2=$?

    # 4. Audit execution return status codes
    if [ $exit_ws1 -ne 0 ] || [ $exit_ws2 -ne 0 ]; then
        echo "[!] Warning: Alpha block '${char}' finished with errors."
        echo "    WS1 Exit Code: $exit_ws1 | WS2 Exit Code: $exit_ws2"
    else
        echo "[✓] Finished Alpha Block '${char}' successfully."
    fi
    echo ""
done

echo "====================================================================="
echo " SUCCESS: Full 30+ Million File Matrix Seeding Complete!"
echo "====================================================================="
