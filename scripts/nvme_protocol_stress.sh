#!/bin/bash
echo "Lighting up advanced VAST NVMe/TCP monitor metrics for 60 seconds..."

# Setup Compare Template
dd if=/dev/zero of=/tmp/4k_zero.bin bs=4k count=1 > /dev/null 2>&1

# 1. Write Zeroes Loop
while true; do sudo nvme write-zeroes /dev/nvme1n2 --start-block=0 --block-count=500 >/dev/null 2>&1; done &
PID_ZERO=$!

# 2. Compare Loop
while true; do sudo nvme compare /dev/nvme1n2 --start-block=0 --block-count=7 --data=/tmp/4k_zero.bin >/dev/null 2>&1; done &
PID_COMP=$!

# 3. Fabric Discovery Loop
while true; do sudo nvme discover -t tcp -a 172.200.203.6 -s 4420 >/dev/null 2>&1; done &
PID_FAB=$!

# 4. Admin Namespace Loop
while true; do sudo nvme id-ns /dev/nvme1n2 >/dev/null 2>&1; done &
PID_ADMIN=$!

# 5. Trim/Unmap Loop
while true; do sudo fstrim -v /mnt/blockhead2 >/dev/null 2>&1; sleep 2; done &
PID_TRIM=$!

# Let them run for 60 seconds
sleep 60

# Cleanup
echo "Cleaning up background stress loops..."
kill $PID_ZERO $PID_COMP $PID_FAB $PID_ADMIN $PID_TRIM
rm /tmp/4k_zero.bin
echo "Done."

