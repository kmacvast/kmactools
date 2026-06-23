#!/usr/bin/env python3
import os
import sys
import json
import random
import tarfile
import logging
import argparse
from typing import Any, Dict, List
import requests

# Setup stdout logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def parse_arguments() -> argparse.Namespace:
    """Parses command-line overrides for paths and endpoints."""
    parser = argparse.ArgumentParser(description="Download and seed the VAST Catalog test dataset.")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG_PATH, help="Path to config database json file.")
    parser.add_argument("--mount-path", type=str, help="Override target NFS mount path.")
    parser.add_argument("--dataset-url", type=str, help="Override source tar.gz dataset URL.")
    return parser.parse_args()

def load_config(config_path: str) -> Dict[str, Any]:
    """Loads configuration properties from the bootstrapped JSON file."""
    if not os.path.exists(config_path):
        logging.error(f"Configuration file not found at {config_path}. Please verify file creation.")
        sys.exit(1)
    try:
        with open(config_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to parse configuration JSON: {e}")
        sys.exit(1)

def download_archive(url: str, target_path: str) -> None:
    """Streams the dataset archive from the internet to a local temporary file."""
    logging.info(f"Downloading source dataset archive from: {url}")
    try:
        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()
        
        with open(target_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        logging.info("Dataset archive download complete.")
    except Exception as e:
        logging.error(f"Failed to download dataset archive: {e}")
        sys.exit(1)

def extract_archive(archive_path: str, target_dir: str) -> None:
    """Extracts tar.gz archive directly into NFS path, natively preserving historical timestamps."""
    logging.info(f"Extracting dataset files into NFS target view path: {target_dir}")
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            # Native extractall restores the archive's internal modification times (mtime)
            tar.extractall(path=target_dir)
        logging.info("Extraction engine pass complete. Historical 2005 timestamps preserved.")
    except Exception as e:
        logging.error(f"Failed to extract tarball archive safely: {e}")
        sys.exit(1)

def seed_dummy_waste(target_dir: str, intensity_percentage: int = 8) -> None:
    """Simulates realistic data waste by scattering junk extensions into random nested folders."""
    logging.info("Starting engineering pass to seed simulated data waste artifacts...")
    
    dummy_extensions: List[str] = [".tmp", ".bak", ".log"]
    dummy_names: List[str] = ["session", "cache", "build_scratch", "old_backup", "debug_dump"]
    
    all_subdirs: List[str] = []
    for root, dirs, _ in os.walk(target_dir):
        for d in dirs:
            all_subdirs.append(os.path.join(root, d))
            
    if not all_subdirs:
        logging.warning("No directories found to seed artifacts into.")
        return

    # Select a random subset of directories based on the chosen intensity
    sample_size = max(1, int(len(all_subdirs) * (intensity_percentage / 100.0)))
    target_subdirs = random.sample(all_subdirs, sample_size)
    
    seeded_count = 0
    for subdir in target_subdirs:
        ext = random.choice(dummy_extensions)
        name = random.choice(dummy_names)
        artifact_filename = f"{name}_{random.randint(100, 999)}{ext}"
        artifact_path = os.path.join(subdir, artifact_filename)
        
        try:
            # Write out small dummy junk blocks (1KB to 250KB) to test space aggregation
            waste_size_bytes = random.randint(1024, 256000)
            with open(artifact_path, "wb") as f:
                f.write(os.urandom(waste_size_bytes))
            seeded_count += 1
        except Exception as e:
            logging.debug(f"Skipped seeding file in {subdir} due to permission/write state: {e}")

    logging.info(f"Seeding completed successfully. Injected {seeded_count} unique waste candidates.")

def main():
    args = parse_arguments()
    config = load_config(args.config)
    
    # Prioritize CLI flags over configuration fields
    target_mount = args.mount_path or config.get("mount_path") or "/mnt/kmacs-root/vast-catalog"
    dataset_url = args.dataset_url or config.get("dataset_url") or "https://cdn.kernel.org/pub/linux/kernel/v2.6/linux-2.6.11.tar.gz"
    
    tmp_archive_path = "/tmp/linux-2.6.11.tar.gz"
    
    # 1. Fetch source payload
    download_archive(dataset_url, tmp_archive_path)
    
    # 2. Extract directly to storage layout
    extract_archive(tmp_archive_path, target_mount)
    
    # 3. Simulate scattered waste footprints
    seed_dummy_waste(target_mount)
    
    # 4. Clean up the system temporary file download
    if os.path.exists(tmp_archive_path):
        os.remove(tmp_archive_path)
        
    logging.info(f"Dataset initialization process finalized. Ready for catalog audit at: {target_mount}")

if __name__ == "__main__":
    main()
