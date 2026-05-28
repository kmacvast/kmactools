import os
import json
import time
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from vastdb import connect

# ==========================================
# 1. GLOBAL VAST BRAND CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="VAST DataBase Telemetry Suite", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Core VAST Palette Definition Strings
VAST_DARK_BG = "#040814"      # Deep Space Core Dark
VAST_CARD_BG = "#0B1124"      # Enclosed Node Slate
VAST_CYAN = "#00E5FF"         # Luminous Active Fabric Line
VAST_BLUE = "#0066FF"         # NVMe Cloud Array Accent
VAST_BORDER = "#1E294B"       # Component Containment Stroke

# Custom CSS Injector for Enterprise Theme Integration
st.markdown(f"""
    <style>
        /* Base Canvas Background Overrides */
        .stApp {{ background-color: {VAST_DARK_BG}; color: #F8FAFC; }}
        .block-container {{ padding-top: 1.5rem; padding-bottom: 1.5rem; }}

        /* FIX: Doubled braces so the f-string passes it to the browser as literal CSS */
        img[alt="st.sidebar.image"] {{ 
            filter: invert(1) brightness(1.8) contrast(1.2); 
        }}        
        
        /* Metric Card Engineering Styles */
        .stMetric {{ 
            background-color: {VAST_CARD_BG}; 
            padding: 1.25rem; 
            border-radius: 8px; 
            border: 1px solid {VAST_BORDER}; 
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);
        }}
        div[data-testid="stMetricValue"] {{ color: #FFFFFF !important; font-weight: 700; }}
        div[data-testid="stMetricLabel"] {{ color: #94A3B8 !important; font-size: 0.85rem; letter-spacing: 0.05em; text-transform: uppercase; }}
        div[data-testid="stMetricDelta"] svg {{ fill: {VAST_CYAN} !important; }}
        
        /* Infrastructure Inventory Blueprint Elements */
        .infra-badge {{ 
            background-color: #02040A; 
            padding: 0.85rem; 
            border-radius: 6px; 
            border: 1px solid {VAST_BORDER};
            border-left: 4px solid {VAST_CYAN}; 
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
            font-size: 0.85rem;
        }}
        .infra-title {{ color: {VAST_CYAN}; font-weight: bold; font-size: 0.75rem; letter-spacing: 0.05em; margin-bottom: 0.25rem; }}
        .infra-val {{ color: #E2E8F0; font-weight: 500; }}
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
# Dynamic Logo Verification Block
LOGO_FILENAME = "vast_logo.png"
if os.path.exists(LOGO_FILENAME):
    # Fixed extension and removed the deprecated use_column_width parameter
    st.sidebar.image(LOGO_FILENAME, width=180)
else:
    # Text fallback branding layout if the logo file hasn't arrived yet
    st.sidebar.markdown(f"## ⚡ VAST DATA")

st.sidebar.markdown(f"**Cluster Engine Link:** `{connection_status}`")
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
    vast_latency_ms = (time.time() - query_start_time) * 1000
except Exception as query_fault:
    st.error(f"Database Query Error: Failed to extract records from VAST fabric: {query_fault}")
    df = pd.DataFrame()
    vast_latency_ms = 0.0

# ==========================================
# 6. ENTERPRISE DASHBOARD RENDER LAYER
# ==========================================
# Main app header structure - Full Width
st.title("📊 VAST DataBase Live Telemetry Suite")
st.markdown(f"Evaluating sub-millisecond market events directly out of multi-protocol tabular flash storage.")

# --- PROOF OF STORAGE INFRASTRUCTURE PLANE ---
st.markdown("### 🛠️ Cluster Architecture Inventory")
infra_col1, infra_col2, infra_col3, infra_col4 = st.columns(4)

with infra_col1:
    st.markdown(f"<div class='infra-badge'><div class='infra-title'>🌐 DATA VIP ENDPOINT</div><div class='infra-val'>{VAST_ENDPOINT}</div></div>", unsafe_allow_html=True)
with infra_col2:
    st.markdown(f"<div class='infra-badge'><div class='infra-title'>🪣 S3 ELEMENT BUCKET</div><div class='infra-val'>s3://{VAST_BUCKET}</div></div>", unsafe_allow_html=True)
with infra_col3:
    st.markdown(f"<div class='infra-badge'><div class='infra-title'>📂 TABULAR SCHEMA</div><div class='infra-val'>/{VAST_SCHEMA}</div></div>", unsafe_allow_html=True)
with infra_col4:
    st.markdown(f"<div class='infra-badge'><div class='infra-title'>📋 TARGET DATABASE TABLE</div><div class='infra-val'>{VAST_TABLE_NAME}</div></div>", unsafe_allow_html=True)

# Output a unified logical path string matching VAST naming specifications
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
            label=f"Current {ticker_choice} Price", 
            value=f"${latest_row['price']:.2f}", 
            delta=f"{price_delta:+} Tick" if price_delta != 0 else "Static"
        )
        kpi2.metric(
            label="Transaction Event Volume", 
            value=f"{int(latest_row['volume']):,}"
        )
        kpi3.metric(
            label="Total Database Records", 
            value=f"{len(df):,} Rows"
        )
        kpi4.metric(
            label="⚡ VAST Fabric Fetch Latency", 
            value=f"{vast_latency_ms:.2f} ms",
            delta="Direct NVMe-oF Read"
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader(f"📈 Real-Time Volatility Matrix: {ticker_choice}")
        
        # VAST Brand Chart Custom Theme Matching Parameters
        chart_theme = {
            "template": "plotly_dark",
            "hovermode": "x unified",
            "font": dict(family="Inter, system-ui, sans-serif", size=12, color="#94A3B8"),
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(0,0,0,0)"
        }
        
        if chart_style == "Interactive Line":
            fig = px.line(df_filtered, x='tick_time', y='price', markers=False)
            fig.update_traces(line=dict(color=VAST_CYAN, width=2.5))
            
        elif chart_style == "Area Shaded":
            fig = px.area(df_filtered, x='tick_time', y='price')
            fig.update_traces(line=dict(color=VAST_BLUE, width=1.5), fillcolor='rgba(0, 102, 255, 0.12)')
            
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
                increasing_line_color=VAST_CYAN, decreasing_line_color='#FF4B4B'
            )])
            fig.update_layout(xaxis_rangeslider_visible=False)

        # Apply VAST Specific Styling Grid Properties
        fig.update_layout(**chart_theme)
        fig.update_xaxes(title_text="Time Partition Slice", showgrid=True, gridcolor='#1E294B', linecolor='#1E294B')
        fig.update_yaxes(title_text="Execution Price ($)", showgrid=True, gridcolor='#1E294B', linecolor='#1E294B', tickformat=".2f")
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