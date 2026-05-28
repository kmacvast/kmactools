import os
import json
import pandas as pd
from vastdb import connect

# Load the exact same config
CONFIG_PATH = os.path.expanduser("~/.vast-ingestor")
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# Connect to VAST data VIP
session = connect(
    endpoint=config["VAST_ENDPOINT"], 
    access=config["VAST_ACCESS_KEY"], 
    secret=config["VAST_SECRET_KEY"]
)

# Open a quick read transaction
with session.transaction() as tx:
    table = tx.bucket(config["VAST_BUCKET"]).schema(config["VAST_SCHEMA"]).table(config["VAST_TABLE_NAME"])
    
    # Select the columns, read them into an Arrow table, and dump to a Pandas DataFrame
    reader = table.select() # Pulls a pyarrow.RecordBatchReader
    arrow_df = reader.read_all().to_pandas()

print(f"\nTotal Ticks Ingested into VAST so far: {len(arrow_df)}")
print("\n--- Last 5 Ticks Added ---")
print(arrow_df.tail(5)[['symbol', 'tick_time', 'price', 'volume']])