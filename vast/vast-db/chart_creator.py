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
        .block-container { padding-top: 2rem; padding-bottom: 2rem; }
        .stMetric { background-color: #1e222b; padding: 1rem; border-radius: 8px; border: 1px solid #2d3139; }
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

# ==========================================
# 3. HIGH-AVAILABILITY CLUSTER CONNECTION
# ==========================================
@st.cache_resource
def get_vast_session():
    return connect(
        endpoint=config["VAST_ENDPOINT"], 
        access=config["VAST_ACCESS_KEY"], 
        secret=config["VAST_SECRET_KEY"]
    )

# Establish status state markers
connection_status = "🔴 Disconnected"
try:
    vast_session = get_vast_session()
    connection_status = "🟢 Connected to VAST Engine"
except Exception as conn_error:
    st.error(f"CRITICAL: Could not reach VAST Data VIP node: {conn_error}")
    st.stop()

# ==========================================
# 4. INTERACTIVE SIDEBAR CONTROL PLANE
# ==========================================
st.sidebar.markdown(f"### 🖥️ Engine Status\n`{connection_status}`")
st.sidebar.markdown("---")
st.sidebar.header("🎛️ Analytics Workspace Tuning")

with st.sidebar.container():
    ticker_choice = st.selectbox("Select Asset Ticker", ["TSLA.US", "AAPL.US", "NVDA.US", "MSFT.US"], index=0)
    chart_style = st.selectbox("Visual Style", ["Interactive Line", "Area Shaded", "OHLC Candlestick"])
    st.markdown("---")
    lookback_ticks = st.slider("Historical Lookback Window (Ticks)", 50, 1000, 200)
    refresh_interval = st.sidebar.slider("UI Frame Refresh Rate (Seconds)", 1, 10, 2)

# ==========================================
# 5. TRANSACTIONAL TRANSACTION SNAPSHOT
# ==========================================
try:
    with vast_session.transaction() as tx:
        table = tx.bucket(config["VAST_BUCKET"]).schema(config["VAST_SCHEMA"]).table(config["VAST_TABLE_NAME"])
        reader = table.select()
        df = reader.read_all().to_pandas()
except Exception as query_fault:
    st.error(f"Database Query Error: Failed to extract records from VAST fabric: {query_fault}")
    df = pd.DataFrame()

# ==========================================
# 6. ENTERPRISE DASHBOARD RENDER LAYER
# ==========================================
# Main app header structure
header_col1, header_col2 = st.columns([0, 1])
with header_col2:
    st.title("📊 VAST DataBase Live Telemetry Suite")
    st.markdown(f"Evaluating sub-millisecond market events directly out of table: `{config['VAST_TABLE_NAME']}`")

st.markdown("---")

if not df.empty:
    # Filter dataset for matching target symbols chronologically
    df_filtered = df[df['symbol'] == ticker_choice].sort_values('tick_time').tail(lookback_ticks)
    
    if df_filtered.empty:
        st.warning(f"⚠️ Telemetry Void: No active data rows found in VAST table for symbol: **{ticker_choice}**.")
    else:
        # Construct Key Performance Indicator Row
        kpi1, kpi2, kpi3 = st.columns(3)
        latest_row = df_filtered.iloc[-1]
        
        # Calculate market ticks delta directionality
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
            label="Total Database Records Ingested", 
            value=f"{len(df):,} Rows"
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

        # Apply standardized business layout configurations
        fig.update_layout(**chart_theme)
        fig.update_xaxes(title_text="Time Partition Slice", showgrid=True, gridcolor='#2d3139', linecolor='#2d3139')
        fig.update_yaxes(title_text="Execution Price ($)", showgrid=True, gridcolor='#2d3139', linecolor='#2d3139', tickformat=".2f")
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=420)
        
        # FIX: Changed use_container_width=True to width='stretch' to match 2026 specs
        st.plotly_chart(fig, width='stretch')

        # Structured lower segment layout 
        st.markdown("---")
        st.subheader("📋 Core Audit Trail Ledger (Tail 5 Rows)")
        
        # Format the dataframe layout seamlessly
        ledger_df = df_filtered.tail(5)[['symbol', 'tick_time', 'price', 'volume', 'turnover', 'seq']].copy()
        ledger_df['tick_time'] = pd.to_datetime(ledger_df['tick_time']).dt.strftime('%Y-%m-%d %H:%M:%S.%f')
        
        # FIX: Changed use_container_width=True to width='stretch' to eliminate warnings
        st.dataframe(ledger_df, width='stretch', hide_index=True)
else:
    st.info("💡 Awaiting Pipeline Ingestion Initialization. Start your python streaming script to activate database nodes.")

# ==========================================
# 7. EXECUTION CONTAINER REFRESH CYCLE
# ==========================================
time.sleep(refresh_interval)
st.rerun()