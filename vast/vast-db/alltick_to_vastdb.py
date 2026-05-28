import os
import json
import time
import threading
import collections
import pandas as pd
import pyarrow as pa
import websocket
from vastdb import connect

# ==========================================
# LOAD EXTERNAL CONFIGURATION
# ==========================================
CONFIG_PATH = os.path.expanduser("~/.vast-ingestor")

if not os.path.exists(CONFIG_PATH):
    raise FileNotFoundError(f"Configuration file not found at {CONFIG_PATH}. Please create it first.")

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

VAST_ENDPOINT = config["VAST_ENDPOINT"]
VAST_ACCESS_KEY = config["VAST_ACCESS_KEY"]
VAST_SECRET_KEY = config["VAST_SECRET_KEY"]
VAST_BUCKET = config["VAST_BUCKET"]
VAST_SCHEMA = config["VAST_SCHEMA"]
VAST_TABLE_NAME = config["VAST_TABLE_NAME"]
# Natively pulled from your ~/.vast-ingestor file
ALLTICK_TOKEN = config["ALLTICK_TOKEN"]

# AllTick Configuration
ALLTICK_WS_URL = f"wss://quote.alltick.co/quote-stock-b-ws-api?token={ALLTICK_TOKEN}"
SYMBOLS_TO_TRACK = ["AAPL.US", "TSLA.US", "NVDA.US", "MSFT.US"]

# Micro-batching tuning
BATCH_SIZE_THRESHOLD = 1000  # Flush after 1,000 rows
BATCH_TIME_THRESHOLD = 2.0    # Or flush every 2 seconds max

# ==========================================
# INITIALIZE VAST DATABASE SCHEMA & TABLE
# ==========================================
print("Connecting to VAST DataBase...")
# FIX: 'access_key' changed to 'access' and 'secret_key' changed to 'secret'
vast_session = connect(endpoint=VAST_ENDPOINT, access=VAST_ACCESS_KEY, secret=VAST_SECRET_KEY)

# Define the optimal PyArrow Schema matching AllTick's feed layout
arrow_schema = pa.schema([
    ('symbol', pa.string()),
    ('tick_time', pa.timestamp('ms')),
    ('price', pa.float64()),
    ('volume', pa.float64()),
    ('turnover', pa.float64()),
    ('trade_direction', pa.int32()),
    ('seq', pa.string())
])

# Metadata setup block inside an explicit transaction context
with vast_session.transaction() as tx:
    bucket = tx.bucket(VAST_BUCKET)
    
    # Try to resolve or create the schema
    try:
        schema = bucket.schema(VAST_SCHEMA)
    except Exception:
        print(f"Schema '{VAST_SCHEMA}' not found. Creating it...")
        schema = bucket.create_schema(VAST_SCHEMA)
        
    # Enforce or create the streaming table
    try:
        vast_table = schema.table(VAST_TABLE_NAME)
        print(f"Verified connection to VAST table: {VAST_TABLE_NAME}")
    except Exception:
        print(f"Table '{VAST_TABLE_NAME}' not found. Creating it now...")
        vast_table = schema.create_table(VAST_TABLE_NAME, arrow_schema)

# Thread-safe data buffer
tick_buffer = collections.deque()
buffer_lock = threading.Lock()
last_flush_time = time.time()

# ==========================================
# PIPELINE STREAM PROCESSING FUNCTIONS
# ==========================================
def flush_buffer_to_vast():
    """Converts the active in-memory buffer into an Arrow Table and appends it via micro-transactions."""
    global last_flush_time
    with buffer_lock:
        if not tick_buffer:
            last_flush_time = time.time()
            return
        
        # Pull records out into a list for processing
        records = [tick_buffer.popleft() for _ in range(len(tick_buffer))]
        last_flush_time = time.time()

    try:
        # Convert list of dicts to Pandas DataFrame, then enforce Arrow formats
        df = pd.DataFrame(records)
        df['tick_time'] = pd.to_datetime(df['tick_time'].astype(float), unit='ms')
        df['price'] = df['price'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['turnover'] = df['turnover'].astype(float)
        df['trade_direction'] = df['trade_direction'].astype(int)

        # Build Arrow Table 
        arrow_table = pa.Table.from_pandas(df, schema=arrow_schema)
        
        # Open a distinct, short-lived transaction block to append this batch
        with vast_session.transaction() as tx:
            tx.bucket(VAST_BUCKET).schema(VAST_SCHEMA).table(VAST_TABLE_NAME).append(arrow_table)
            
        print(f"[VAST] Transaction committed! {len(records)} ticks successfully stored.")
    except Exception as e:
        print(f"[ERROR] Failed to commit batch to VAST DataBase: {e}")

def check_timer_loop():
    """Background thread worker that guarantees flushes happen at regular intervals."""
    while True:
        time.sleep(0.5)
        if (time.time() - last_flush_time) >= BATCH_TIME_THRESHOLD:
            if len(tick_buffer) > 0:
                flush_buffer_to_vast()

# ==========================================
# WEBSOCKET CALLING INTERFACE
# ==========================================
def on_message(ws, message):
    data = json.loads(message)
    
    # Filter for standard market data pushes
    if "price" in data or ("data" in data and isinstance(data.get("data"), dict)):
        tick_payload = data if "price" in data else data.get("data")
        
        # Map incoming short-hand API tags to structured VAST columns
        tick_info = {
            "symbol": tick_payload.get("code"),
            "tick_time": tick_payload.get("tick_time"),
            "price": tick_payload.get("price"),
            "volume": tick_payload.get("volume", 0),
            "turnover": tick_payload.get("turnover", 0),
            "trade_direction": tick_payload.get("trade_direction", 0),
            "seq": str(tick_payload.get("seq", ""))
        }
        
        # Append data to processing stream queue
        with buffer_lock:
            tick_buffer.append(tick_info)
            buffer_size = len(tick_buffer)
        
        # Flush if size metrics are met
        if buffer_size >= BATCH_SIZE_THRESHOLD:
            flush_buffer_to_vast()

def on_error(ws, error):
    print(f"[WS ERROR] Connection encountered anomaly: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"[WS CLOSED] Stream connection broke off. Retrying... Status: {close_status_code}")

def on_open(ws):
    print("WebSocket Handshake established. Subscribing to stock tickers...")
    
    # AllTick Protocol Number 22004: Real-time tick data batch subscription
    subscribe_msg = {
        "cmd_id": 22004,
        "seq_id": int(time.time()),
        "trace": "vast-db-stress-test-trace",
        "data": {
            "symbol_list": [{"code": sym} for sym in SYMBOLS_TO_TRACK]
        }
    }
    ws.send(json.dumps(subscribe_msg))
    print(f"Active Subscriptions pushed for: {SYMBOLS_TO_TRACK}")

if __name__ == "__main__":
    # Launch background safety flushing thread
    timer_thread = threading.Thread(target=check_timer_loop, daemon=True)
    timer_thread.start()

    # Create the WebSocket App
    ws = websocket.WebSocketApp(
        ALLTICK_WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever(ping_interval=10)