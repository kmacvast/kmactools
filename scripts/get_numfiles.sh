#!/bin/bash

# --- Virtual Environment Auto-Activation ---
VENV_PATH="$HOME/ingestor-venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

export VMS_ADDRESS="var202.selab.vastdata.com"
export VMS_USER="admin"

# --- Credential Ingestion Layer ---
if [ -n "$1" ]; then
    export VMS_PASSWORD="$1"
elif [ -n "$VMS_PASSWORD" ]; then
    export VMS_PASSWORD="$VMS_PASSWORD"
else
    read -s -p "Enter VAST VMS Password for admin: " VMS_PASSWORD
    echo "" 
    export VMS_PASSWORD
fi

if [ -z "$VMS_PASSWORD" ]; then
    echo "[!] Error: Password string cannot be empty."
    exit 1
fi

echo -e "\n========================================================"
echo -e " STEP 1: Fetching Initial Quota Status"
echo -e "========================================================"
vastpy-cli get quotas fields=path,used_capacity_tb,used_inodes | grep -E "path|kmacs"

echo -e "\n========================================================"
echo -e " STEP 2: Dynamically Discovering & Registering Workspaces"
echo -e "========================================================"

# Register base anchor pathways
vastpy-cli post quotas path="/kmacs/vast-catalog/linux-2.6.11" name="idx_linux" > /dev/null 2>&1
vastpy-cli post quotas path="/kmacs/vast-catalog/workspace_1" name="idx_ws1" > /dev/null 2>&1

# Define the local mount root to scan for active directories
MOUNT_SCAN_ZONE="/mnt/kmacs-root/vast-catalog"

if [ -d "$MOUNT_SCAN_ZONE" ]; then
    echo "[*] Scanning active mount layer: $MOUNT_SCAN_ZONE"
    
    # Loop through anything matching workspace_* (covers alpha, numeric, or custom markers)
    for dir in "$MOUNT_SCAN_ZONE"/workspace_*; do
        if [ -d "$dir" ]; then
            folder_name=$(basename "$dir")
            vast_path="/kmacs/vast-catalog/$folder_name"
            quota_name="idx_$folder_name"
            
            echo "  -> Found target: $folder_name | Syncing cluster context..."
            vastpy-cli post quotas path="$vast_path" name="$quota_name" > /dev/null 2>&1
        fi
    done
    echo "[✓] Dynamic metadata registration sweep completed across the storage tier."
else
    echo "[!] Error: Mount path $MOUNT_SCAN_ZONE not accessible. Skipping discovery loop."
fi

echo -e "\n========================================================"
echo -e " STEP 3: Pausing 3 Seconds for Metadata Aggregation..."
echo -e "========================================================"
sleep 3

echo -e "\n========================================================"
echo -e " STEP 4: Final File Count Breakdown (used_inodes)"
echo -e "========================================================"
vastpy-cli get quotas fields=path,used_capacity_tb,used_inodes | grep -E "path|kmacs" | sort -k3 -t'|'
echo -e "========================================================\n"
