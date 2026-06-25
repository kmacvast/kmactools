#!/usr/bin/env python3
import os
import json
import datetime
import vastdb
from ibis import _

# --- Configuration Settings ---
CATALOG_PATH_PREFIX = "/kmacs/vast-catalog"
DEFAULT_CONFIG_PATH = os.path.expanduser("~/.vast-catalog-config.json")

def main():
    with open(DEFAULT_CONFIG_PATH, "r") as f:
        config = json.load(f)

    session = vastdb.connect(
        endpoint=config.get("vast_endpoint"),
        access=config.get("access_key"),
        secret=config.get("secret_key"),
        ssl_verify=False
    )

    # Pull everything modified in the last 3 hours to capture all recent runs
    time_window = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=3)
    
    print("\n[1] Pulling recent metadata updates from VAST Catalog...")
    
    with session.transaction() as tx:
        catalog_table = tx.catalog()
        projection = ['name', 'extension', 'parent_path', 'mtime']

        reader = catalog_table.select(
            columns=projection,
            predicate=(
                (_.parent_path.startswith(CATALOG_PATH_PREFIX)) &
                (_.mtime >= time_window)
            )
        )
        table = reader.read_all()

    df = table.to_pandas()
    print(f" -> Total recent database records retrieved: {len(df):,}")

    if df.empty:
        print("\n [!] Diagnostic Result: Zero files found in the catalog for the last 3 hours.")
        print("     The background VAST Catalog snapshot engine hasn't indexed the new files yet.")
        return

    # Scan the text client-side using Pandas string manipulation
    matched = df[df['name'].str.contains('locked', case=False, na=False)]
    print(f" -> Total records containing 'locked' found client-side: {len(matched):,}")

    if not matched.empty:
        print("\n[2] DIAGNOSTIC INSPECTION (First 3 Matches):")
        print("=" * 90)
        for idx, row in matched.head(3).iterrows():
            print(f"  RAW NAME      : '{row['name']}'")
            print(f"  RAW EXTENSION : '{row['extension']}'")
            print(f"  DATABASE PATH :  {row['parent_path']}/")
            print("-" * 90)
        print("=" * 90)
        print("\n[3] Action Item:")
        print("  Look at 'RAW EXTENSION' above. If it shows '' (empty string) or something unexpected,")
        print("  that explains why our database extension filter came up empty!")
    else:
        print("\n [!] Diagnostic Result: Found recent files in the database, but NONE contain 'locked'.")
        print("     This indicates the new ZIP files are not yet committed to the database view.")
        print("     Verify that the files actually exist on the Linux mount point.")

if __name__ == "__main__":
    main()
