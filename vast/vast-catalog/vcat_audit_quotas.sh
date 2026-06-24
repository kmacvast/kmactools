#!/bin/bash
# ==============================================================================
# SCRIPT NAME : vcat_audit_quotas.sh
# DESCRIPTION : Automated multi-workspace discovery and telemetry aggregation
#               engine. Dynamically scans the storage tier mount layer, auto-
#               registers newly created alpha/numeric testing blocks into the
#               VAST Cluster management plane via vastpy-cli quotas, and renders
#               a cleanly sorted real-time inode and capacity dashboard.
#
# AUTHOR      : KMac & Sheila
# DATE        : June 23, 2026
# VERSION     : 2.1.0
# LICENSE     : MIT / Enterprise Internal
#
# DEPENDENCIES: bash, vastpy-cli, ingestor-venv (Python Venv)
#
# ==============================================================================
# REVISION HISTORY:
# Date       | Version | Author         | Summary of Changes
# -----------+---------+----------------+---------------------------------------
# 2026-06-23 | 2.1.0   | KMac & Sheila  | Implemented --brief option flag to 
#            |         |                | suppress Steps 1-3 output for automation.
# 2026-06-23 | 2.0.0   | KMac & Sheila  | Fixed ASCII table sorting collision,
#            |         |                | decoupled the headers from sort pipelines,
#            |         |                | and filtered out rogue test paths.
# 2026-06-23 | 1.0.0   | KMac & Sheila  | Initial framework deployment with
#            |         |                | workspace discovery loop automation.
# ==============================================================================
# USAGE EXAMPLES:
#   # 1. Standard execution (Will interactively prompt securely for VMS password):
#   ./vcat_audit_quotas.sh
#
#   # 2. Automated inline injection (Pass password directly as argument string):
#   ./vcat_audit_quotas.sh "SecretClusterPassword123"
#
#   # 3. Brief execution mode (Only prints final breakdown matrix):
#   ./vcat_audit_quotas.sh --brief
#   ./vcat_audit_quotas.sh "SecretClusterPassword123" --brief
#
#   # 4. Environment Variable Injection (For non-interactive crons/pipelines):
#   export VMS_PASSWORD="SecretClusterPassword123" && ./vcat_audit_quotas.sh --brief
# ==============================================================================

# --- Virtual Environment Auto-Activation ---
VENV_PATH="$HOME/ingestor-venv/bin/activate"
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
fi

export VMS_ADDRESS="var202.selab.vastdata.com"
export VMS_USER="admin"

# --- Advanced Argument Parsing ---
BRIEF=false
PASS_INPUT=""

for arg in "$@"; do
    if [ "$arg" == "--brief" ]; then
        BRIEF=true
    else
        # Any non-flag argument is assumed to be the password injection
        PASS_INPUT="$arg"
    fi
done

# --- Credential Ingestion Layer ---
if [ -n "$PASS_INPUT" ]; then
    export VMS_PASSWORD="$PASS_INPUT"
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

# --- STEP 1: Fetching Initial Quota Status ---
if [ "$BRIEF" = false ]; then
    echo -e "\n========================================================"
    echo -e " STEP 1: Fetching Initial Quota Status"
    echo -e "========================================================"
    vastpy-cli get quotas fields=path,used_capacity_tb,used_inodes | grep -E "used_inodes|kmacs"
fi

# --- STEP 2: Dynamically Discovering & Registering Workspaces ---
if [ "$BRIEF" = false ]; then
    echo -e "\n========================================================"
    echo -e " STEP 2: Dynamically Discovering & Registering Workspaces"
    echo -e "========================================================"
fi

vastpy-cli post quotas path="/kmacs/vast-catalog/linux-2.6.11" name="idx_linux" > /dev/null 2>&1
vastpy-cli post quotas path="/kmacs/vast-catalog/workspace_1" name="idx_ws1" > /dev/null 2>&1

MOUNT_SCAN_ZONE="/mnt/kmacs-root/vast-catalog"

if [ -d "$MOUNT_SCAN_ZONE" ]; then
    if [ "$BRIEF" = false ]; then
        echo "[*] Scanning active mount layer: $MOUNT_SCAN_ZONE"
    fi

    for dir in "$MOUNT_SCAN_ZONE"/workspace_*; do
        if [ -d "$dir" ]; then
            folder_name=$(basename "$dir")
            vast_path="/kmacs/vast-catalog/$folder_name"
            quota_name="idx_$folder_name"

            if [ "$BRIEF" = false ]; then
                echo "  -> Found target: $folder_name | Syncing cluster context..."
            fi
            vastpy-cli post quotas path="$vast_path" name="$quota_name" > /dev/null 2>&1
        fi
    done
    
    if [ "$BRIEF" = false ]; then
        echo "[✓] Dynamic metadata registration sweep completed across the storage tier."
    fi
else
    if [ "$BRIEF" = false ]; then
        echo "[!] Error: Mount path $MOUNT_SCAN_ZONE not accessible. Skipping discovery loop."
    fi
fi

# --- STEP 3: Pausing 3 Seconds for Metadata Aggregation ---
if [ "$BRIEF" = false ]; then
    echo -e "\n========================================================"
    echo -e " STEP 3: Pausing 3 Seconds for Metadata Aggregation..."
    echo -e "========================================================"
fi
sleep 3

# --- STEP 4: Final File Count Breakdown ---
echo -e "\n========================================================"
echo -e " STEP 4: Final File Count Breakdown (used_inodes)"
echo -e "========================================================"

echo "used_inodes |used_capacity_tb |path"
echo "------------+-----------------+---------------------------------+"

vastpy-cli get quotas fields=path,used_capacity_tb,used_inodes | grep "kmacs" | sort -k3 -t'|'
echo -e "========================================================\n"
