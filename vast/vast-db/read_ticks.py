import os
import json
import time
import pandas as pd
from vastdb import connect

# Load the exact same external configuration
CONFIG_PATH = os.path.expanduser("~/.vast-ingestor")
if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}.")

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# ANSI terminal control strings for UI styling
CLEAR_SCREEN = "\033[H\033[2J"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"

print(f"{CYAN}Initializing connection to VAST DataBase...{RESET}")
session = connect(
    endpoint=config["VAST_ENDPOINT"], 
    access=config["VAST_ACCESS_KEY"], 
    secret=config["VAST_SECRET_KEY"]
)

try:
    while True:
        # Open a short-lived read transaction to grab a fresh point-in-time snapshot
        with session.transaction() as tx:
            table = tx.bucket(config["VAST_BUCKET"]).schema(config["VAST_SCHEMA"]).table(config["VAST_TABLE_NAME"])
            reader = table.select()
            df = reader.read_all().to_pandas()

        # Wipe the terminal cleanly for the next refresh frame
        print(CLEAR_SCREEN, end="")
        
        print(f"{BOLD}{YELLOW}===================================================={RESET}")
        print(f"{BOLD}{YELLOW}          VAST DATA LIVE TICK MONITOR               {RESET}")
        print(f"{BOLD}{YELLOW}===================================================={RESET}\n")
        
        print(f"{BOLD}Total Records Committed to Storage Fabric:{RESET} {GREEN}{len(df):,}{RESET}")
        
        if not df.empty:
            print(f"\n{BOLD}{CYAN}[ LATEST TICKER QUOTES ]{RESET}")
            print(f"----------------------------------------------------")
            
            # Sort chronologically, group by asset, and pull the latest state row
            latest_prices = df.sort_values('tick_time').groupby('symbol').last().reset_index()
            for _, row in latest_prices.iterrows():
                print(f" 📈 {BOLD}{row['symbol']:<8}{RESET} | Price: ${GREEN}{row['price']:<7.2f}{RESET} | Last Vol: {int(row['volume']):<5}")
            
            print(f"\n{BOLD}{CYAN}[ STREAMING TRANSACTION PIPE (Tail 5) ]{RESET}")
            print(f"----------------------------------------------------")
            
            # Isolate the latest 5 records and clean up the presentation timestamps
            tail_df = df.tail(5)[['symbol', 'tick_time', 'price', 'volume']].copy()
            tail_df['tick_time'] = pd.to_datetime(tail_df['tick_time']).dt.strftime('%H:%M:%S')
            
            # Output beautifully formatted text strings without index columns
            print(tail_df.to_string(index=False))
        else:
            print("\n[!] Data layer empty. Awaiting stream processing events...")
            
        print(f"\n{YELLOW}Refreshing dashboard frame every 1s... Press Ctrl+C to halt.{RESET}")
        time.sleep(1)

except KeyboardInterrupt:
    print(f"\n\n{YELLOW}[INFO] Live telemetry stream closed out.{RESET}\n")