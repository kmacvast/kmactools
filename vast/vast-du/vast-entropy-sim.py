#!/usr/bin/env python3
################################################################################
# Script Name:    vast-entropy-sim.py
# Description:    Simulates high-velocity data ingestion by generating logs 
#                 with varying entropy levels (high vs. low compressibility).
#                 Uses multiprocessing to maximize throughput and provides 
#                 real-time EPS (Events Per Second) monitoring.
#                 
# Author:         KMac kmac@vastdata.com
# Created:        2026-04-09
# Version:        1.0.0
# 
# Dependencies:   - Python 3.x
#                 - Standard library (multiprocessing, json, uuid, etc.)
################################################################################

import os
import time
import json
import uuid
import secrets
import random
import multiprocessing
from datetime import datetime, UTC  # Added UTC here

# --- CONFIGURATION ---
PROCS_PER_TYPE = 4
LOG_DIR_HIGH = "./logs/high_comp"
LOG_DIR_LOW = "./logs/low_comp"
BATCH_SIZE = 1000   # Increased slightly for better high-speed efficiency

# Shared counters for the monitor
high_count = multiprocessing.Value('i', 0)
low_count = multiprocessing.Value('i', 0)

def generate_high_comp_line():
    """Generates highly repetitive data"""
    event = {
        # Fix: Using datetime.now(UTC) instead of utcnow()
        "timestamp": datetime.now(UTC).isoformat(),
        "level": random.choice(["INFO", "DEBUG", "WARN"]),
        "component": random.choice(["Auth", "DB", "UI"]),
        "message": "Standard repetitive operational log message for routine maintenance.",
        "region": "us-east-1"
    }
    return json.dumps(event)

def generate_low_comp_line():
    """Generates high-entropy data"""
    event = {
        # Fix: Using datetime.now(UTC) instead of utcnow()
        "timestamp": datetime.now(UTC).isoformat(),
        "session": str(uuid.uuid4()),
        "entropy": secrets.token_hex(32),
        "metric": random.random()
    }
    return json.dumps(event)

def worker(proc_id, data_type, counter):
    folder = LOG_DIR_HIGH if data_type == "high" else LOG_DIR_LOW
    os.makedirs(folder, exist_ok=True)
    filename = os.path.join(folder, f"proc_{data_type}_{proc_id}.log")

    while True:
        with open(filename, "a") as f:
            batch = []
            for _ in range(BATCH_SIZE):
                line = generate_high_comp_line() if data_type == "high" else generate_low_comp_line()
                batch.append(line + "\n")
            f.writelines(batch)

        with counter.get_lock():
            counter.value += BATCH_SIZE

def monitor():
    print(f"\n{'Time':<10} | {'High Comp EPS':<15} | {'Low Comp EPS':<15} | {'Total EPS':<10}")
    print("-" * 65)
    last_high = 0
    last_low = 0
    while True:
        time.sleep(1)
        curr_high = high_count.value
        curr_low = low_count.value
        eps_high = curr_high - last_high
        eps_low = curr_low - last_low

        # Output results with comma formatting for readability
        print(f"{datetime.now().strftime('%H:%M:%S'):<10} | {eps_high:<15,} | {eps_low:<15,} | {eps_high+eps_low:<10,}")

        last_high, last_low = curr_high, curr_low

if __name__ == "__main__":
    processes = []

    # Clean setup
    for d in [LOG_DIR_HIGH, LOG_DIR_LOW]:
        if not os.path.exists(d):
            os.makedirs(d)

    # Launch processes
    for i in range(PROCS_PER_TYPE):
        p_high = multiprocessing.Process(target=worker, args=(i, "high", high_count))
        p_low = multiprocessing.Process(target=worker, args=(i, "low", low_count))
        p_high.start()
        p_low.start()
        processes.append(p_high)
        processes.append(p_low)

    try:
        monitor()
    except KeyboardInterrupt:
        print("\nShutting down workers...")
        for p in processes:
            p.terminate()
            p.join()
        print("Done.")
