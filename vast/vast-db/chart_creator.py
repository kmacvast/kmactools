import os
import json
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from vastdb import connect

# 1. Page Configuration Setup
st.set_page_config(page_title="VAST Live Analytics", layout="wide")

# 2. Extract Your Native Cluster Profile Config
CONFIG_PATH = os.path.expanduser("~/.vast-ingestor")
if not os.path.exists(CONFIG_PATH):
    st.error(f"Configuration file missing at {CONFIG_PATH}")
    st.stop()

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

# 3. Cache the VAST Session Connection Resource
@st.cache_resource
def get_vast_session():
    return connect(
        endpoint=config["VAST_ENDPOINT"], 
        access=config["VAST_ACCESS_KEY"], 
        secret=config["VAST_SECRET_KEY"]
    )

try:
    vast_session = get_vast_session()
except Exception as conn_error:
    st.error(f"Could not reach VAST Data VIP: {conn_error}")
    st.stop()

# 4. Dashboard Title Mechanics
st.title("📊 VAST DataBase Live Chart Creator")
st.markdown("Querying live transactional snapshots directly out of the flash-backed tabular storage engine.")

# 5. Interactive Sidebar Controls
st.sidebar.header("🎛️ Chart Tuning Options")
ticker_choice = st.sidebar.selectbox("Select Asset Ticker", ["TSLA.US", "AAPL.US", "NVDA.US", "MSFT.US"], index=0)
chart_style = st.sidebar.selectbox("Visual Style", ["Interactive Line", "Area Shaded", "OHLC Candlestick"])
lookback_ticks = st.sidebar.slider("Historical Lookback (Ticks)", 50, 1000, 200)
refresh_interval = st.sidebar.slider("UI Refresh Interval (Seconds)", 1, 10, 2)

# 6. Execute Analytical DB Snapshot Block
try:
    with vast_session.transaction() as tx:
        table = tx.bucket(config["VAST_BUCKET"]).schema(config["VAST_SCHEMA"]).table(config["VAST_TABLE_NAME"])
        reader = table.select()
        df = reader.read_all().to_pandas()
except Exception as query_fault:
    st.error(f"Failed to extract records from VAST: {query_fault}")
    df = pd.DataFrame()

# 7. Chart Rendering Engine Logic
if not df.empty:
    # Filter for selected symbol and slice lookback timeline
    df_filtered = df[df['symbol'] == ticker_choice].sort_values('tick_time').tail(lookback_ticks)
    
    if df_filtered.empty:
        st.warning(f"No active data points found in VAST for symbol: {ticker_choice}. Check if ingestion script is running.")
    else:
        # Build Real-Time KPI Cards
        kpi1, kpi2, kpi3 = st.columns(3)
        latest_row = df_filtered.iloc[-1]
        
        # Compute real price deltas from previous tick
        price_delta = round(latest_row['price'] - df_filtered.iloc[-2]['price'], 2) if len(df_filtered) > 1 else 0.0
        
        kpi1.metric(label=f"Current {ticker_choice} Price", value=f"${latest_row['price']:.2f}", delta=f"{price_delta:+}")
        kpi2.metric(label="Last Transaction Volume", value=f"{int(latest_row['volume'])}")
        kpi3.metric(label="Global Database Row Count", value=f"{len(df):,}")
        
        # Build Selected Plotly Layout 
        st.subheader(f"Live Market Profile: {ticker_choice}")
        
        if chart_style == "Interactive Line":
            fig = px.line(df_filtered, x='tick_time', y='price', markers=True, template="plotly_dark")
            fig.update_traces(line_color='#00CC96')
            
        elif chart_style == "Area Shaded":
            fig = px.area(df_filtered, x='tick_time', y='price', template="plotly_dark")
            fig.update_traces(line_color='#636EFA', fillcolor='rgba(99, 110, 250, 0.15)')
            
        elif chart_style == "OHLC Candlestick":
            # Resample raw ticks into 1-minute financial intervals
            df_filtered['minute_bucket'] = pd.to_datetime(df_filtered['tick_time']).dt.to_period('Min')
            ohlc = df_filtered.groupby('minute_bucket').agg(
                open=('price', 'first'), high=('price', 'max'),
                low=('price', 'min'), close=('price', 'last'),
                time=('tick_time', 'first')
            ).reset_index()
            
            fig = go.Figure(data=[go.Candlestick(
                x=ohlc['time'], open=ohlc['open'], high=ohlc['high'],
                low=ohlc['low'], close=ohlc['close']
            )])
            fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False)

        # Apply Global Styling Configurations
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=400, xaxis_title="Timestamp", yaxis_title="Execution Price ($)")
        st.plotly_chart(fig, use_container_width=True)

        # Raw Tabular Readout
        st.subheader("Raw Data Blocks (Tail 5)")
        st.dataframe(df_filtered.tail(5), use_container_width=True)
else:
    st.info("Awaiting initial system events. Start your alltick_to_vastdb.py script to populate data.")

# 8. Trigger Controlled UI Loop Refresh
time.sleep(refresh_interval)
st.rerun()