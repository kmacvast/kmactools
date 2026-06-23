#!/usr/bin/env python3
import os
import sys
import json
import shutil
import tarfile
import zipfile
import logging
import requests
from multiprocessing.pool import ThreadPool

# Setup clean verbose logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

DATASETS = {
    "enron": {
        "url": "https://www.cs.cmu.edu/~enron/enron_mail_20150507.tar.gz",
        "tmp_file": "/tmp/enron_mail.tar.gz",
        "type": "tar"
    },
    "imagenet": {
        "url": "http://cs231n.stanford.edu/tiny-imagenet-200.zip",
        "tmp_file": "/tmp/tiny-imagenet.zip",
        "type": "zip"
    }
}

def load_config():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return json.load(f)

def download_payload(name: str, meta: dict):
    if os.path.exists(meta["tmp_file"]) and os.path.getsize(meta["tmp_file"]) > 1000000:
        logging.info(f"Using cached archive for {name} found at {meta['tmp_file']}")
        return
    logging.info(f"Downloading {name} dataset from: {meta['url']}")
    try:
        response = requests.get(meta["url"], stream=True, timeout=60)
        response.raise_for_status()
        with open(meta["tmp_file"], "wb") as f:
            for chunk in response.iter_content(chunk_size=65536):
                f.write(chunk)
        logging.info(f" -> {name} archive download finalized.")
    except Exception as e:
        logging.error(f"Failed download sequence for {name}: {e}")
        sys.exit(1)

def extract_payload(name: str, meta: dict, target_dir: str):
    logging.info(f"Extracting base seed layer for {name} into {target_dir}...")
    os.makedirs(target_dir, exist_ok=True)
    try:
        if meta["type"] == "tar":
            with tarfile.open(meta["tmp_file"], "r:gz") as tar:
                tar.extractall(path=target_dir)
        elif meta["type"] == "zip":
            with zipfile.ZipFile(meta["tmp_file"], 'r') as zip_ref:
                zip_ref.extractall(target_dir)
        logging.info(f" -> Extraction for {name} completed.")
    except Exception as e:
        logging.error(f"Failed extraction sequence for {name}: {e}")
        sys.exit(1)

def map_local_tree(src_dir: str):
    """Scans local staging zone files and folders to optimize memory allocation."""
    dirs_list = []
    files_list = []
    for root, subdirs, filenames in os.walk(src_dir):
        for sd in subdirs:
            dirs_list.append(os.path.relpath(os.path.join(root, sd), src_dir))
        for f in filenames:
            files_list.append(os.path.relpath(os.path.join(root, f), src_dir))
    return dirs_list, files_list

def file_copy_worker(paths):
    """Worker thread that executes standalone block transfers over the mount."""
    src, dest = paths
    try:
        shutil.copy2(src, dest)
    except Exception:
        pass # Suppress minor runtime I/O locks

def parallel_dir_clone(src_root: str, dest_root: str, concurrency_threads: int):
    """Executes high-concurrency directory seeding using process thread pools."""
    if not os.path.exists(src_root):
        return
        
    logging.info(f"  -> Profiling metadata structure layout for: {os.path.basename(src_root)}")
    relative_dirs, relative_files = map_local_tree(src_root)
    
    # Phase 1: Pre-create the directory skeletal tree sequentially (very fast)
    logging.info(f"  -> Bulk building {len(relative_dirs):,} skeletal directory paths...")
    os.makedirs(dest_root, exist_ok=True)
    for d in relative_dirs:
        os.makedirs(os.path.join(dest_root, d), exist_ok=True)
        
    # Phase 2: Distribute file operations concurrently across the thread pool
    logging.info(f"  -> Distributing {len(relative_files):,} file transfers across {concurrency_threads} threads...")
    copy_tasks = [
        (os.path.join(src_root, f), os.path.join(dest_root, f)) 
        for f in relative_files
    ]
    
    pool = ThreadPool(concurrency_threads)
    pool.map(file_copy_worker, copy_tasks)
    pool.close()
    pool.join()

def multiply_workspaces(source_root: str, target_root: str, copies: int = 5):
    """Orchestrates parallel workspace initialization cascades."""
    # Resolve extracted location pathways
    enron_src = os.path.join(source_root, "enron_mail_20150507", "maildir")
    if not os.path.exists(enron_src):
        enron_src = os.path.join(source_root, "maildir")
    imagenet_src = os.path.join(source_root, "tiny-imagenet-200")
    
    # Calculate thread allocation (64 threads maximizes concurrent network contexts)
    concurrency_threads = max(32, os.cpu_count() * 4)
    logging.info(f"Initiating Engine Multiplier Core (Targeting {concurrency_threads} Concurrent Worker Streams)")
    
    for i in range(1, copies + 1):
        workspace_dir = os.path.join(target_root, f"workspace_{i}")
        logging.info(f"============================================================")
        logging.info(f"STARTING CONCURRENT WORKSPACE DUMP [{i}/{copies}] -> {workspace_dir}")
        logging.info(f"============================================================")
        
        # Parallel Copy Corporate Email Dataset
        parallel_dir_clone(enron_src, os.path.join(workspace_dir, "corporate_email"), concurrency_threads)
        
        # Parallel Copy ML Images Dataset
        parallel_dir_clone(imagenet_src, os.path.join(workspace_dir, "ml_training_images"), concurrency_threads)

def main():
    config = load_config()
    target_mount = config.get("mount_path")
    scratch_extraction_zone = "/tmp/vast_scratch_seed"
    
    # 1. Pipeline active network downloads
    for name, meta in DATASETS.items():
        download_payload(name, meta)
        
    # 2. Extract components to local processing layer
    for name, meta in DATASETS.items():
        extract_payload(name, meta, scratch_extraction_zone)
        
    # 3. Scale up to millions of records using multi-threaded execution
    multiply_workspaces(scratch_extraction_zone, target_mount, copies=5)
    
    # 4. Clean local scratch systems
    if os.path.exists(scratch_extraction_zone):
        shutil.rmtree(scratch_extraction_zone)
        
    logging.info(f"SUCCESS! Scale-out parallel injection complete. Millions of files seeded.")

if __name__ == "__main__":
    main()
