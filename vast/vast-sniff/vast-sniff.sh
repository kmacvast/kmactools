#!/usr/bin/env bash
#############################################################################
# 
#  Script:    vast-sniff.sh
#  Author:    KMac
#  Date:      May 5th, 2026
# 
#  Notes: 
#  1/ log onto the leader node (find-leader) 
#  2/ Then attach to the platform container using /vast/data/attachdocker.sh
# 
#############################################################################

LABEL="fruit"
DTS=$(date +%Y%m%d%H%M)
CLIENT_IP="1.2.3.4"
OUT_DIR="/vast/log"
FILENAME="${OUT_DIR}/tcpdump_${LABEL}_${DTS}.pcap"

if [[ $EUID -ne 0 ]]; then
   echo "Error: This script must be run as root (use sudo)."
   exit 1
fi

if [[ -z "$CLIENT_IP" ]]; then
    echo "Error: CLIENT_IP is not defined."
    exit 1
fi

if [[ -z "$LABEL" ]]; then
    echo "Error: LABEL is empty."
    exit 1
fi

if [[ ! "$LABEL" =~ ^[a-zA-Z0-9]+$ ]]; then
    echo "Error: LABEL '$LABEL' is invalid. Use only letters and numbers (no spaces)."
    exit 1
fi

SECONDS=0

summary() {
    local duration=$SECONDS
    echo -e "\n\n--- Capture Summary ---"
    echo "Status:      Capture Stopped"
    echo "Duration:    $((duration / 60))m $((duration % 60))s"
    echo "Destination: $FILENAME"
    
    # Check if file was actually created and show size
    if [[ -f "$FILENAME" ]]; then
        du -h "$FILENAME" | awk '{print "File Size:   " $1}'
    fi
    echo "-----------------------"
}

trap summary EXIT

echo "Starting packet capture on host ${CLIENT_IP}..."
echo "Filter: host ${CLIENT_IP}"
echo "Press Ctrl+C to stop."

tcpdump -Z root -i any -w "$FILENAME" host "$CLIENT_IP"



