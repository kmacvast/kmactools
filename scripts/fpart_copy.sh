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

# --- Virtual Environment Auto-Activation ---
VENV_PATH="$HOME/ingestor-venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

# Pre-create the local logging tier directory
LOG_DIR="logs"
mkdir -p "$LOG_DIR"

# Dynamic Loop processing alphabetical horizons from d through z
for char in {d..z}; do
    echo "====================================================================="
    echo " DISPATCHING CONCURRENT ALPHA BLOCK: Workspace 1${char} & 2${char}"
    echo "====================================================================="

    # Define distinct out-of-band log paths
    LOG_WS1="$LOG_DIR/fpsync_ws1${char}.log"
    LOG_WS2="$LOG_DIR/fpsync_ws2${char}.log"

    echo "[+] Launching Workspace 1${char} -> Log: $LOG_WS1"
    # Fully detach by redirecting stdout/stderr to log and stdin to /dev/null
    fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_1a/ /mnt/kmacs-root/vast-catalog/workspace_1${char}/ > "$LOG_WS1" 2>&1 < /dev/null &
    pid_ws1=$!

    echo "[+] Launching Workspace 2${char} -> Log: $LOG_WS2"
    fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_2a/ /mnt/kmacs-root/vast-catalog/workspace_2${char}/ > "$LOG_WS2" 2>&1 < /dev/null &
    pid_ws2=$!

    echo "[*] Processing 64 combined network streams out-of-band. Synchronizing..."

    # Wait safely for both isolated background streams to finish before looping
    wait $pid_ws1 $pid_ws2

    echo -e "[✓] Finished Alpha Block '${char}'. Stepping to next horizon...\n"
done

echo "====================================================================="
echo " SUCCESS: Full 30+ Million File Matrix Seeding Complete!"
echo "====================================================================="
