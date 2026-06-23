#!/bin/bash

# Run fpsync with 32 parallel execution workers
# fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_1a/ /mnt/kmacs-root/vast-catalog/workspace_1c/
# fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_2a/ /mnt/kmacs-root/vast-catalog/workspace_2c/
#

# Define runtime log directory inside the repository framework
LOG_DIR="$HOME/kmactools/scripts/logs"
mkdir -p "$LOG_DIR"

# Dynamic Loop processing alphabetical horizons from d through z
for char in {d..z}; do
    echo "====================================================================="
    echo " STARTING CONCURRENT ALPHA BLOCK: Workspace 1${char} & 2${char}"
    echo "====================================================================="
    
    # 1. Fire Workspace 1 Copy into background with total TTY/stdin isolation
    fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_1a/ /mnt/kmacs-root/vast-catalog/workspace_1${char}/ > "$LOG_DIR/fpsync_ws1${char}.log" 2>&1 < /dev/null &
    pid_ws1=$!
    echo "[+] Launched Workspace 1${char} Parallel Job (PID: $pid_ws1) -> Log: logs/fpsync_ws1${char}.log"
    
    # 2. Fire Workspace 2 Copy into background with total TTY/stdin isolation
    fpsync -n 32 -v /mnt/kmacs-root/vast-catalog/workspace_2a/ /mnt/kmacs-root/vast-catalog/workspace_2${char}/ > "$LOG_DIR/fpsync_ws2${char}.log" 2>&1 < /dev/null &
    pid_ws2=$!
    echo "[+] Launched Workspace 2${char} Parallel Job (PID: $pid_ws2) -> Log: logs/fpsync_ws2${char}.log"
    
    echo "[*] Synchronizing parallel threads... Processing 64 combined network streams out-of-band."
    
    # 3. Wait for BOTH parallel copy operations to finish before moving to the next letter
    wait $pid_ws1 $pid_ws2
    
    echo -e "[✓] Finished Alpha Block '${char}'. Stepping to next horizon...\n"
done

echo "====================================================================="
echo " SUCCESS: Full 30+ Million File Matrix Seeding Complete!"
echo "====================================================================="
