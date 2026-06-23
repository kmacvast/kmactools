#!/usr/bin/env python3
import os
import sys
import json
import logging
import boto3
import pandas as pd
import vastdb
from ibis import _

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def load_config():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        return json.load(f)

def tag_files_via_s3(config: dict):
    """Connects via S3 Protocol to add tracking tags to the NFS-created files."""
    logging.info("Connecting to storage data plane via S3 protocol client...")
    
    s3_client = boto3.client(
        's3',
        endpoint_url=config.get("vast_endpoint"),
        aws_access_key_id=config.get("access_key"),
        aws_secret_access_key=config.get("secret_key"),
        verify=False
    )
    
    bucket_name = "kmacs-vast-catalog-test-bucket"
    target_mount = config.get("mount_path")
    files_to_tag = []
    
    for root, _, files in os.walk(target_mount):
        for file in files:
            if file.endswith('.tmp'):
                relative_key = os.path.relpath(os.path.join(root, file), target_mount)
                files_to_tag.append(relative_key)
                if len(files_to_tag) >= 5:
                    break
        if len(files_to_tag) >= 5:
            break

    logging.info(f"Injecting custom S3 object tags onto {len(files_to_tag)} target assets...")
    for key in files_to_tag:
        s3_client.put_object_tagging(
            Bucket=bucket_name,
            Key=key,
            Tagging={
                'TagSet': [
                    {'Key': 'security_review', 'Value': 'quarantined'},
                    {'Key': 'owner', 'Value': 'catalog_team'}
                ]
            }
        )
        logging.info(f" -> Tagged Object: {key} [security_review=quarantined]")

def query_custom_tags(config: dict):
    """Queries the VAST Catalog database looking strictly for our new custom tag values."""
    logging.info("Opening database transaction to scan for updated metadata tags...")
    
    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )
    
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        # Corrected: Using 'user_tags' as verified by your dump_schema output
        projection = ['name', 'parent_path', 'user_tags', 'element_type']
        
        reader = catalog_table.select(
            columns=projection,
            predicate=_.parent_path.startswith("/kmacs/vast-catalog")
        )
        table = reader.read_all()
        
    df = table.to_pandas()
    
    # Safe parser handling for PyArrow Map layouts inside Pandas
    def matches_tag(tags):
        if not tags:
            return False
        if isinstance(tags, dict):
            return tags.get('security_review') == 'quarantined'
        for item in tags:
            if isinstance(item, dict) and item.get('key') == 'security_review' and item.get('value') == 'quarantined':
                return True
            if isinstance(item, tuple) and len(item) >= 2 and item[0] == 'security_review' and item[1] == 'quarantined':
                return True
        return False

    df['is_quarantined'] = df['user_tags'].apply(matches_tag)
    df_results = df[df['is_quarantined'] == True]
    
    print("\n" + "="*80)
    print("               VAST CATALOG CUSTOM TAG QUERY RESULTS                    ")
    print("="*80)
    print(f"Total Quarantined Files Located via Catalog: {len(df_results)}")
    print("-"*80)
    if df_results.empty:
        print(" [!] No indexed tags matched yet. (Waiting on background crawler sync...)")
    else:
        for idx, row in df_results.head(10).iterrows():
            print(f" FILE: {row['name']:<30} | PATH: {row['parent_path']}")
    print("="*80 + "\n")

def main():
    config = load_config()
    
    # 1. Apply tags via S3 data plane
    tag_files_via_s3(config)
    
    # 2. Query the catalog database
    query_custom_tags(config)

if __name__ == "__main__":
    main()
