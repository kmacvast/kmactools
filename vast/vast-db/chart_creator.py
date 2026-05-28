import os
import json
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from vastdb import connect

# ==========================================
# 1. GLOBAL PAGE & BRAND CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="VAST DataBase Analytics Suite", 
    page_icon="📊", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom enterprise styling injector
st.markdown("""
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 1.5rem; }
        .stMetric { background-color: #1e222b; padding: 1rem; border-radius: 8px; border: 1px solid #2d3139; }
        .infra-badge { background-color: #10141d; padding: 0.75rem; border-radius: 6px; border-left: 4px solid #636EFA; font-family: monospace; }
        div[data-testid="stMetricDelta"] svg { fill: #00CC96 !important; }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. RUNTIME CONFIGURATION PROFILE EXTRACTION
# ==========================================
CONFIG_PATH = os.path.expanduser("~/.vast-ingestor")
if not os.path.exists(CONFIG_PATH):
    st.error(f"❌ System Fault: Configuration file missing at {CONFIG_PATH}")
    st.stop()

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

VAST_ENDPOINT = config["VAST_ENDPOINT"]
VAST_BUCKET = config["VAST_BUCKET"]
VAST_SCHEMA = config["VAST_SCHEMA"]
VAST_TABLE_NAME = config["VAST_TABLE_NAME"]

# ==========================================
# 3. HIGH-AVAILABILITY CLUSTER CONNECTION
# ==========================================
@st.cache_resource
def get_vast_session():
    return connect(
        endpoint=VAST_ENDPOINT, 
        access=config["VAST_ACCESS_KEY"], 
        secret=config["VAST_SECRET_KEY"]
    )

connection_status = "🔴 Disconnected"
try:
    vast_session = get_vast_session()
    connection_status = "🟢 Connected"
except Exception as conn_error:
    st.error(f"CRITICAL: Could not reach VAST Data VIP node: {conn_error}")
    st.stop()

# ==========================================
# 4. INTERACTIVE SIDEBAR CONTROL PLANE
# ==========================================
st.sidebar.markdown(f"### 🖥️ Cluster Engine\n`{connection_status}`")
st.sidebar.markdown("---")
st.sidebar.header("🎛️ Analytics Workspace Tuning")

with st.sidebar.container():
    ticker_choice = st.selectbox("Select Asset Ticker", ["TSLA.US", "AAPL.US", "NVDA.US", "MSFT.US"], index=0)
    chart_style = st.selectbox("Visual Style", ["Interactive Line", "Area Shaded", "OHLC Candlestick"])
    st.markdown("---")
    lookback_ticks = st.slider("Historical Lookback Window (Ticks)", 50, 1000, 200)
    refresh_interval = st.sidebar.slider("UI Frame Refresh Rate (Seconds)", 1, 10, 2)

# ==========================================
# 5. INSTRUMENTED TRANSACTION BLOCK
# ==========================================
query_start_time = time.time()
try:
    with vast_session.transaction() as tx:
        table = tx.bucket(VAST_BUCKET).schema(VAST_SCHEMA).table(VAST_TABLE_NAME)
        reader = table.select()
        df = reader.read_all().to_pandas()
    # Calculate exact delta in milliseconds
    vast_latency_ms = (time.time() - query_start_time) * 1000
except Exception as query_fault:
    st.error(f"Database Query Error: Failed to extract records from VAST fabric: {query_fault}")
    df = pd.DataFrame()
    vast_latency_ms = 0.0

# ==========================================
# 6. ENTERPRISE DASHBOARD RENDER LAYER
# ==========================================
st.title("📊 VAST DataBase Live Telemetry Suite")
st.markdown("Evaluating sub-millisecond market events directly out of multi-protocol tabular flash storage.")

# --- PROOF OF STORAGE INFRASTRUCTURE PLANE ---
st.markdown("### 🛠️ Cluster Architecture Inventory")
infra_col1, infra_col2, infra_col3, infra_col4 = st.columns(4)

with infra_col1:
    st.markdown(f"<div class='infra-badge'><b>🌐 DATA VIP ENDPOINT</b><br>{VAST_ENDPOINT}</div>", unsafe_allow_html=True)
with infra_col2:
    st.markdown(f"<div class='infra-badge'><b>🪣 S3 ELEMENT BUCKET</b><br>s3://{VAST_BUCKET}</div>", unsafe_allow_html=True)
with infra_col3:
    st.markdown(f"<div class='infra-badge'><b>📂 TABULAR SCHEMA</b><br>/{VAST_SCHEMA}</div>", unsafe_allow_html=True)
with infra_col4:
    st.markdown(f"<div class='infra-badge'><b>📋 TARGET DATABASE TABLE</b><br>{VAST_TABLE_NAME}</div>", unsafe_allow_html=True)

# Output a unified logical path string
st.caption(f"**Logical Object URI:** `vast://{VAST_ENDPOINT.replace('http://', '')}/{VAST_BUCKET}/{VAST_SCHEMA}/{VAST_TABLE_NAME}`")

st.markdown("---")

if not df.empty:
    df_filtered = df[df['symbol'] == ticker_choice].sort_values('tick_time').tail(lookback_ticks)
    
    if df_filtered.empty:
        st.warning(f"⚠️ Telemetry Void: No active data rows found in VAST table for symbol: **{ticker_choice}**.")
    else:
        # Construct Key Performance Indicator Row
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        latest_row = df_filtered.iloc[-1]
        
        price_delta = round(latest_row['price'] - df_filtered.iloc[-2]['price'], 2) if len(df_filtered) > 1 else 0.0
        
        kpi1.metric(
            label=f"Last Cleared {ticker_choice} Value", 
            value=f"${latest_row['price']:.2f}", 
            delta=f"{price_delta:+} Market Tick" if price_delta != 0 else "Static"
        )
        kpi2.metric(
            label="Transaction Event Volume", 
            value=f"{int(latest_row['volume']):,}"
        )
        kpi3.metric(
            label="Total Database Records", 
            value=f"{len(df):,} Rows"
        )
        # Highlight performance metric to display VAST speed
        kpi4.metric(
            label="⚡ VAST Fabric Fetch Latency", 
            value=f"{vast_latency_ms:.2f} ms",
            delta="Direct NVMe-oF Read"
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader(f"📈 Real-Time Volatility Matrix: {ticker_choice}")
        
        # Initialize uniform Plotly design template configs
        chart_theme = {
            "template": "plotly_dark",
            "hovermode": "x unified",
            "font": dict(family="Inter, system-ui, sans-serif", size=12),
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)"
        }
        
        if chart_style == "Interactive Line":
            fig = px.line(df_filtered, x='tick_time', y='price', markers=False)
            fig.update_traces(line=dict(color='#00CC96', width=2))
            
        elif chart_style == "Area Shaded":
            fig = px.area(df_filtered, x='tick_time', y='price')
            fig.update_traces(line=dict(color='#636EFA', width=1.5), fillcolor='rgba(99, 110, 250, 0.12)')
            
        elif chart_style == "OHLC Candlestick":
            df_filtered['minute_bucket'] = pd.to_datetime(df_filtered['tick_time']).dt.to_period('Min')
            ohlc = df_filtered.groupby('minute_bucket').agg(
                open=('price', 'first'), high=('price', 'max'),
                low=('price', 'min'), close=('price', 'last'),
                time=('tick_time', 'first')
            ).reset_index()
            
            fig = go.Figure(data=[go.Candlestick(
                x=ohlc['time'], open=ohlc['open'], high=ohlc['high'],
                low=ohlc['low'], close=ohlc['close'],
                increasing_line_color='#00CC96', decreasing_line_color='#FF4B4B'
            )])
            fig.update_layout(xaxis_rangeslider_visible=False)

        fig.update_layout(**chart_theme)
        fig.update_xaxes(title_text="Time Partition Slice", showgrid=True, gridcolor='#2d3139', linecolor='#2d3139')
        fig.update_yaxes(title_text="Execution Price ($)", showgrid=True, gridcolor='#2d3139', linecolor='#2d3139', tickformat=".2f")
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=420)
        
        st.plotly_chart(fig, width='stretch')

        st.markdown("---")
        st.subheader("📋 Core Audit Trail Ledger (Tail 5 Rows)")
        
        ledger_df = df_filtered.tail(5)[['symbol', 'tick_time', 'price', 'volume', 'turnover', 'seq']].copy()
        ledger_df['tick_time'] = pd.to_datetime(ledger_df['tick_time']).dt.strftime('%Y-%m-%d %H:%M:%S.%f')
        
        st.dataframe(ledger_df, width='stretch', hide_index=True)
else:
    st.info("💡 Awaiting Pipeline Ingestion Initialization. Start your python streaming script to activate database nodes.")

# ==========================================
# 7. EXECUTION CONTAINER REFRESH CYCLE
# ==========================================
time.sleep(refresh_interval)
st.rerun()