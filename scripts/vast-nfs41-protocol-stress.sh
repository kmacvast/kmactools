#!/bin/bash
# Check for root privileges
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (sudo)."
  exit 1
fi

MOUNT_POINT="/mnt/nfs41test"

# Verify mount point exists and is an nfs4 mount
if ! mount | grep -q "$MOUNT_POINT type nfs4"; then
  echo "[!] Error: $MOUNT_POINT is not active or is not mounted as NFSv4/v4.1."
  exit 1
fi

echo "======================================================================"
echo " LAUNCHING VAST NFSv4.1 PROTOCOL FEATURE & TRAFFIC EXERCISER          "
echo "======================================================================"
echo " -> Target Mount: $MOUNT_POINT"
echo " -> Exercising: Compounding, State Delegations, POSIX Byte-Locks,"
echo "                Attribute Caching (SETATTR/GETATTR), & Parallel I/O  "
echo "----------------------------------------------------------------------"
echo " [+] RUNNING FOREVER. Press [Ctrl + C] to cleanly abort everything.   "
echo "======================================================================"

# DEFINE THE CRITICAL CTRL+C CLEANUP TRAP
cleanup() {
  echo -e "\n\n[!] Caught Ctrl-C! Cleaning up background traffic loops..."

  # Kill active background processes safely
  kill $PID_FIO $PID_META $PID_ATTR $PID_LOCK 2>/dev/null

  # Clean up test files
  rm -rf "$MOUNT_POINT/meta_stress" "$MOUNT_POINT/lock_stress.dat" "$MOUNT_POINT/attr_stress.txt" 2>/dev/null

  echo "[+] All stress testing loops terminated cleanly. Exiting."
  exit 0
}
# Tie the cleanup function to Ctrl+C (INT) and termination (TERM) signals
trap cleanup INT TERM

# ----------------------------------------------------------------------
# LOOP A: Native NFSv4 Byte-Range Locking Stress
# ----------------------------------------------------------------------
echo "[+] Starting NFSv4 Byte-Range Locking loop..."
touch "$MOUNT_POINT/lock_stress.dat"
while true; do
  # Utilizing flock to force the NFSv4.1 client to acquire and release stateful locks
  (
    flock -x 200
    echo "$(date): Lock Acquired By Process $$" >> "$MOUNT_POINT/lock_stress.dat"
  ) 200>"$MOUNT_POINT/lock_stress.dat"
  sleep 0.1
done &
PID_LOCK=$!

# ----------------------------------------------------------------------
# LOOP B: Metadata Compounding & Open/Close State Stress
# ----------------------------------------------------------------------
echo "[+] Starting Metadata & Compounding Stress (OPEN/CLOSE/LOOKUP/REMOVE)..."
while true; do
  # Rapidly build deep trees to force COMPOUND RPC structures
  mkdir -p "$MOUNT_POINT/meta_stress/dir_{1..5}"
  for i in {1..40}; do
    touch "$MOUNT_POINT/meta_stress/dir_$((1 + RANDOM % 5))/file_$i"
  done
  # Read attributes/lookup via recursive directory listing
  ls -lR "$MOUNT_POINT/meta_stress" >/dev/null 2>&1
  # Destroy and repeat
  rm -rf "$MOUNT_POINT/meta_stress"
  sleep 0.2
done &
PID_META=$!

# ----------------------------------------------------------------------
# LOOP C: Attribute & Access Control Stress (SETATTR / GETATTR)
# ----------------------------------------------------------------------
echo "[+] Starting NFSv4 Attribute Tuning Loop (GETATTR/SETATTR)..."
touch "$MOUNT_POINT/attr_stress.txt"
while true; do
  chmod 777 "$MOUNT_POINT/attr_stress.txt"
  # Attempt typical ownership updates to trigger ID mapper evaluations
  chown nobody:nogroup "$MOUNT_POINT/attr_stress.txt" 2>/dev/null || chown nobody:nobody "$MOUNT_POINT/attr_stress.txt" 2>/dev/null
  chmod 600 "$MOUNT_POINT/attr_stress.txt"
  stat "$MOUNT_POINT/attr_stress.txt" >/dev/null 2>&1
  sleep 0.1
done &
PID_ATTR=$!

# ----------------------------------------------------------------------
# LOOP D: Core FIO Parallel I/O Engine
# ----------------------------------------------------------------------
echo "[+] Spawning core FIO high-concurrency engine (with POSIX locking mode)..."
while true; do
  sudo fio --time_based --runtime=60 --ioengine=io_uring --direct=1 --group_reporting=0 \
    --directory="$MOUNT_POINT" \
    --name=nfs41_posix_locks --filename=fio_locks.bin --rw=randrw --bs=4k --iodepth=16 --numjobs=4 --size=1g --lockmode=posix \
    --name=nfs41_heavy_iops --filename=fio_iops.bin --rw=randrw --rwmixread=70 --bs=4k --iodepth=64 --numjobs=4 --size=2g \
    --name=nfs41_seq_bw --filename=fio_bw.bin --rw=read --bs=1m --iodepth=16 --numjobs=2 --size=4g >/dev/null 2>&1
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
