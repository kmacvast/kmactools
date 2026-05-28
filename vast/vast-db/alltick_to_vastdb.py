import json
import time
import threading
import collections
import pandas as pd
import pyarrow as pa
import websocket
from vastdb import connect

# ==========================================
# CONFIGURATION
# ==========================================
# VAST DataBase Connection Settings
VAST_ENDPOINT = "http://var202.selab.vastdata.com:80"
VAST_ACCESS_KEY = "TSSBZ5ZYQB1FXGVP12FW"
VAST_SECRET_KEY = "UV8+lWJ1ZBJqdMzJe3q2H6Z1SKwXGeSVN4HSpyuc"
VAST_BUCKET = "tickdata"
VAST_SCHEMA = "realtime"
VAST_TABLE_NAME = "alltick_ticks"

# AllTick Configuration
# Note: Substitute 'testtoken' with your free token from alltick.co if required
ALLTICK_TOKEN = "testtoken" 
ALLTICK_WS_URL = f"wss://quote.alltick.co/quote-stock-b-ws-api?token={ALLTICK_TOKEN}"
SYMBOLS_TO_TRACK = ["AAPL.US", "TSLA.US", "NVDA.US", "MSFT.US"]

# Micro-batching tuning
BATCH_SIZE_THRESHOLD = 1000  # Flush after 1,000 rows
BATCH_TIME_THRESHOLD = 2.0    # Or flush every 2 seconds max

# ==========================================
# INITIALIZE VAST DATABASE SCHEMA
# ==========================================
print("Connecting to VAST DataBase...")
vast_session = connect(endpoint=VAST_ENDPOINT, access_key=VAST_ACCESS_KEY, secret_key=VAST_SECRET_KEY)
bucket = vast_session.bucket(VAST_BUCKET)
schema = bucket.schema(VAST_SCHEMA)

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

# Safeguard table creation
try:
    vast_table = schema.table(VAST_TABLE_NAME)
    print(f"Connected to existing VAST table: {VAST_TABLE_NAME}")
except Exception:
    print(f"Table {VAST_TABLE_NAME} not found. Creating it now...")
    vast_table = schema.create_table(name=VAST_TABLE_NAME, schema=arrow_schema)

# Thread-safe data buffer
tick_buffer = collections.deque()
buffer_lock = threading.Lock()
last_flush_time = time.time()

# ==========================================
# PIPELINE STREAM PROCESSING FUNCTIONS
# ==========================================
def flush_buffer_to_vast():
    """Converts the active in-memory buffer into an Arrow Table and appends it to VAST."""
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

        # Build Arrow Table and commit to VAST
        arrow_table = pa.Table.from_pandas(df, schema=arrow_schema)
        vast_table.append(arrow_table)
        print(f"[VAST] Flushed batch of {len(records)} ticks to storage successfully.")
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
    
    # AllTick protocol pushes tick events with structural payload contents
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

    # Maintain the execution loop. 
    # AllTick drops connections if no activity occurs for 30s. 
    # ping_interval=10 sends a native WebSocket ping frame every 10 seconds.
    ws.run_forever(ping_interval=10)