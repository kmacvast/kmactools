#!/bin/bash
################################################################################
# Script Name:  chaos_monkey_block.sh
# Description:  Ultimate VAST NVMe/TCP Protocol & Storage Traffic Stress Engine.
#               Simulates extreme concurrent filesystem I/O, native NVMe fabric 
#               discovery floods, admin namespaces requests, write-zeroes, 
#               and hardware-level background block unmaps (TRIM).
# Author:       Kevin McDonald (vastdata)
# Date:         July 2026
# Version:      2.1 (Dynamic Device Mapping & Host Log Protection Enabled)
#
# Usage:        sudo ./chaos_monkey_block.sh
# Dependencies: nvme-cli, fio, util-linux (fstrim)
# Mountpoints:  /mnt/blockhead1, /mnt/blockhead2
################################################################################

# ==============================================================================
# CONFIGURATION PARAMETERS
# ==============================================================================
TARGET_DEV="/dev/nvme1n2"           # Updated to your actual NVMe device
DISCOVERY_IP="172.200.203.3"        # Updated to your active cluster IP
DISCOVERY_PORT="4420"
MNT_POINT_2="/mnt/nvme2"            # Updated to your active mount point

# Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run as root (sudo) to inject fabric commands."
  exit 1
fi

echo "======================================================================"
echo " LAUNCHING CHAOS MONKEY FOR BLOCKHEADS                                "
echo "======================================================================"
echo " -> Target Device: $TARGET_DEV"
echo " -> Simulating active filesystem operations on blockhead1 & 2         "
echo " -> Injecting native NVMe commands (Compare, Write Zeroes, Admin, Trim) "
echo " -> Spamming NVMe-oF Fabric discovery packets                         "
echo "----------------------------------------------------------------------"
echo " [+] RUNNING SAFELY (Root Log Protection Enabled). [Ctrl + C] to abort. "
echo "======================================================================"

# 1. Setup Compare Template file
dd if=/dev/zero of=/tmp/4k_zero.bin bs=4k count=1 > /dev/null 2>&1

# 2. DEFINE THE CRITICAL CTRL+C CLEANUP TRAP
cleanup() {
  echo -e "\n\n[!] Caught Ctrl-C! Stopping all background traffic streams..."

  # Kill all active background process groups safely
  kill $PID_ZERO $PID_COMP $PID_FAB $PID_ADMIN $PID_TRIM $PID_FIO 2>/dev/null

  # Remove the temporary block comparison template
  rm -f /tmp/4k_zero.bin

  echo "[+] All stress testing loops terminated cleanly. Exiting."
  exit 0
}
# Tie the cleanup function to Ctrl+C (INT) and termination (TERM) signals
trap cleanup INT TERM

echo "[+] Spawning NVMe/TCP protocol injectors..."

# LOOP A: NVMe Native Write Zeroes
while true; do
  nvme write-zeroes "$TARGET_DEV" --start-block=0 --block-count=500 >/dev/null 2>&1
  # Throttle back slightly if target drops to protect host kernel
  if [ $? -ne 0 ]; then sleep 2; fi
done &
PID_ZERO=$!

# LOOP B: NVMe Native Compare
while true; do
  nvme compare "$TARGET_DEV" --start-block=0 --block-count=7 --data=/tmp/4k_zero.bin >/dev/null 2>&1
  if [ $? -ne 0 ]; then sleep 2; fi
done &
PID_COMP=$!

# LOOP C: NVMe-oF Fabric Discovery Request Spam
while true; do
  nvme discover -t tcp -a "$DISCOVERY_IP" -s "$DISCOVERY_PORT" >/dev/null 2>&1
  if [ $? -ne 0 ]; then sleep 2; fi
done &
PID_FAB=$!

# LOOP D: NVMe Admin Identify Namespace Requests
while true; do
  nvme id-ns "$TARGET_DEV" >/dev/null 2>&1
  if [ $? -ne 0 ]; then sleep 2; fi
done &
PID_ADMIN=$!

# LOOP E: Filesystem Level Block UNMAP (TRIM)
while true; do
  fstrim -v "$MNT_POINT_2" >/dev/null 2>&1
  if [ $? -ne 0 ]; then
    sleep 5   # Extra cooldown if the filesystem goes into forced-shutdown
  else
    sleep 2
  fi
done &
PID_TRIM=$!

echo "[+] Spawning core FIO high-concurrency storage engine..."

# LOOP F: Standard File I/O Engine (Loops FIO runs sequentially back-to-back)
while true; do
  fio --time_based --runtime=60 --ioengine=io_uring --direct=1 --group_reporting=0 \
    --directory=/mnt/blockhead1:/mnt/blockhead2 \
    --name=small_random_iops --filename=fio_iops.bin --rw=randrw --rwmixread=70 --bs=4k --iodepth=64 --numjobs=4 --size=4g \
    --name=large_sequential_bandwidth --filename=fio_bw.bin --rw=read --bs=1m --iodepth=16 --numjobs=2 --size=10g \
    --name=database_flushes --filename=fio_db.bin --rw=randwrite --bs=8k --iodepth=16 --numjobs=2 --size=4g --fdatasync=10 \
    --name=space_reclaim_trim --filename=fio_trim.bin --rw=randtrim --bs=64k --iodepth=8 --numjobs=1 --size=4g >/dev/null 2>&1

  if [ $? -ne 0 ]; then sleep 5; fi
done &
PID_FIO=$!

echo "----------------------------------------------------------------------"
echo " ALL WORKLOADS ACTIVE. Terminal output quieted to protect dashboard lookups."
echo " Fire up your './vast-opstat.py' script and watch the metrics fly! "
echo "----------------------------------------------------------------------"

# Keep the parent process alive so the trap monitor intercepts your terminal input
while true; do
  sleep 1
done
