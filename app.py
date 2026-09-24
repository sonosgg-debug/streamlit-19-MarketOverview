"""
Streamlit Market Overview Dashboard
Ultra-lightweight, 100% Python-based implementation of MarketOverview
Preserves the exact content layout and dark Glassmorphism visual design.
"""

import streamlit as st
from datetime import datetime, timezone, timedelta
KST = timezone(timedelta(hours=9))
from config import CATEGORIES, US_MARKET_TICKERS, K_MARKET_TICKERS, SEMI_MARKET_TICKERS
from market_data import fetch_all_market_data
from card_component import render_card_grid

# Page config
st.set_page_config(
    page_title="Market Overview",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Glassmorphism & Dark Theme
CUSTOM_CSS = """
<style>
/* Base Dark Background */
.stApp {
    background-color: #09090b !important;
    color: #f4f4f5 !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* Hide Streamlit Header & Footer */
header[data-testid="stHeader"] {
    background: transparent !important;
}
footer {
    display: none !important;
}

/* Main Content Area Padding */
.main .block-container,
[data-testid="stMainBlockContainer"] {
    padding-top: 2.0rem !important;
}

/* Main Dashboard Title (00 Bookmarks #8AB4F8 Soft Sky Blue) */
h1, .main-title, [data-testid="stMarkdownContainer"] h1 {
    color: #8AB4F8 !important;
    -webkit-text-fill-color: #8AB4F8 !important;
    font-size: 2.0rem !important;
    font-weight: 800 !important;
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #f8fafc !important;
    -webkit-text-fill-color: #f8fafc !important;
}

/* Glassmorphism Card Grid */
.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    gap: 18px;
    margin-top: 14px;
    margin-bottom: 24px;
}

/* Glassmorphism Card */
.glass-card {
    background: rgba(24, 24, 27, 0.7) !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(138, 180, 248, 0.55) !important;
    border-radius: 12px !important;
    padding: 18px 20px !important;
    min-height: 145px !important;
    display: flex !important;
    flex-direction: column !important;
    justify-content: space-between !important;
    transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease, border-color 0.2s ease !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(138, 180, 248, 0.12) !important;
    position: relative !important;
    overflow: hidden !important;
}

.glass-card:hover {
    transform: translateY(-4px) !important;
    border-color: rgba(138, 180, 248, 0.85) !important;
    box-shadow: 0 12px 28px -6px rgba(0, 0, 0, 0.6), 0 0 16px rgba(138, 180, 248, 0.25) !important;
    background: rgba(30, 30, 34, 0.85) !important;
}

/* Card Header */
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 10px;
}

.card-title {
    font-size: 13.5px;
    font-weight: 500;
    color: #a1a1aa;
    line-height: 1.35;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 95%;
}

/* Card Body */
.card-body {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 12px;
}

.price-container {
    display: flex;
    flex-direction: column;
    flex-shrink: 0;
    max-width: 48%;
}

.price-row {
    display: flex;
    align-items: center;
    gap: 4px;
}

.price-value {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.02em;
    color: #fafafa;
}

.change-row {
    display: flex;
    align-items: center;
    font-size: 13.5px;
    font-weight: 500;
    margin-top: 4px;
}

.sparkline-container {
    opacity: 0.9;
    transition: opacity 0.2s ease;
    position: relative;
    overflow: visible !important;
    display: flex;
    justify-content: flex-end;
    align-items: flex-end;
    width: 50%;
    min-width: 165px;
}

.glass-card:hover .sparkline-container {
    opacity: 1;
}

/* Sparkline Interactive Tooltip & Crosshair */
.sp-hover-group {
    cursor: crosshair;
}

.sp-hover-hit {
    pointer-events: all !important;
}

.sp-hover-group .sp-tip,
.sp-hover-group .sp-cross,
.sp-hover-group .sp-dot {
    display: none;
    pointer-events: none !important;
}

.sp-hover-group:hover .sp-tip,
.sp-hover-group:hover .sp-cross,
.sp-hover-group:hover .sp-dot {
    display: block !important;
}

/* Tabs Styling */
div[data-baseweb="tab-list"] {
    gap: 8px;
    background-color: transparent !important;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
    padding-bottom: 6px;
    margin-bottom: 12px;
}

button[data-baseweb="tab"] {
    border-radius: 8px !important;
    color: #a1a1aa !important;
    padding: 8px 18px !important;
    font-weight: 500 !important;
    font-size: 15px !important;
    background: transparent !important;
    border: none !important;
    transition: all 0.15s ease !important;
}

button[data-baseweb="tab"]:hover {
    color: #ffffff !important;
    background: rgba(255, 255, 255, 0.05) !important;
}

button[data-baseweb="tab"][aria-selected="true"] {
    color: #38bdf8 !important;
    background: rgba(56, 189, 248, 0.12) !important;
    font-weight: 600 !important;
}

div[data-baseweb="tab-highlight"] {
    background-color: #38bdf8 !important;
    height: 2px !important;
}

/* Streamlit Button Styling */
div.stButton > button {
    background: rgba(255, 255, 255, 0.06) !important;
    color: #e4e4e7 !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 8px !important;
    padding: 6px 14px !important;
    font-size: 13.5px !important;
    transition: all 0.2s ease !important;
}

div.stButton > button:hover {
    background: rgba(255, 255, 255, 0.12) !important;
    border-color: rgba(255, 255, 255, 0.25) !important;
    color: #ffffff !important;
}

/* Sidebar Container */
section[data-testid="stSidebar"] {
    background-color: #0d1117 !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

section[data-testid="stSidebar"] > div {
    padding-top: 1.5rem !important;
}

/* =========================================================
   사이드바 접기(<<) 및 펼치기(>>) 버튼 항상 표시 및 시인성/대비 강화 (00 Bookmarks 스타일)
   ========================================================= */
/* 1. 사이드바가 열려 있을 때 접기 버튼 (<<) 상시 표시 */
[data-testid="stSidebarCollapseButton"] {
    visibility: visible !important;
    opacity: 1 !important;
    display: inline-flex !important;
}

[data-testid="stSidebarCollapseButton"] button {
    visibility: visible !important;
    opacity: 1 !important;
    background-color: #1e293b !important;       /* 진한 네이비 배경 */
    border: 1.5px solid #38bdf8 !important;     /* 선명한 스카이블루 테두리로 상자 명확화 */
    border-radius: 8px !important;
    width: 38px !important;
    height: 38px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
    transition: all 0.2s ease !important;
}

/* 상자 내부의 << 아이콘(Material Icon span/svg/문자)을 순백색으로 강제하여 상자와 극명한 대비 구현 */
[data-testid="stSidebarCollapseButton"] button *,
[data-testid="stSidebarCollapseButton"] span,
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
[data-testid="stSidebarCollapseButton"] svg {
    color: #ffffff !important;
    fill: #ffffff !important;
    opacity: 1 !important;
    visibility: visible !important;
    font-size: 1.35rem !important;
    font-weight: 700 !important;
}

/* 호버(PC) 및 터치 시 반전 효과 */
[data-testid="stSidebarCollapseButton"] button:hover {
    background-color: #38bdf8 !important;
    border-color: #38bdf8 !important;
}
[data-testid="stSidebarCollapseButton"] button:hover * {
    color: #0f172a !important;
    fill: #0f172a !important;
}

/* 2. 사이드바 헤더 영역 패딩 및 정렬 보정 */
[data-testid="stSidebarHeader"] {
    padding-top: 0.5rem !important;
    padding-bottom: 0.5rem !important;
}

/* 3. 사이드바가 닫혔을 때 다시 여는 버튼 (>>) 시인성 강화 */
[data-testid="stSidebarCollapsedControl"] {
    visibility: visible !important;
    opacity: 1 !important;
    display: block !important;
    z-index: 999999 !important;
}

[data-testid="stSidebarCollapsedControl"] button {
    background-color: #1e293b !important;
    border: 1.5px solid #38bdf8 !important;
    border-radius: 8px !important;
    width: 38px !important;
    height: 38px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.4), 0 0 6px rgba(56, 189, 248, 0.2) !important;
    transition: all 0.2s ease !important;
}

[data-testid="stSidebarCollapsedControl"] button *,
[data-testid="stSidebarCollapsedControl"] span,
[data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
[data-testid="stSidebarCollapsedControl"] svg {
    color: #38bdf8 !important;
    fill: #38bdf8 !important;
    opacity: 1 !important;
    visibility: visible !important;
    font-size: 1.35rem !important;
}

[data-testid="stSidebarCollapsedControl"] button:hover {
    background-color: #38bdf8 !important;
    border-color: #38bdf8 !important;
}

[data-testid="stSidebarCollapsedControl"] button:hover * {
    color: #0f172a !important;
    fill: #0f172a !important;
}

/* Sidebar Radio Buttons Styling */
section[data-testid="stSidebar"] div[role="radiogroup"] {
    gap: 8px !important;
}

section[data-testid="stSidebar"] div[role="radiogroup"] label {
    background: rgba(255, 255, 255, 0.04) !important;
    border: 1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
    transition: all 0.2s ease !important;
    width: 100% !important;
    cursor: pointer !important;
}

section[data-testid="stSidebar"] div[role="radiogroup"] label:hover {
    background: rgba(255, 255, 255, 0.08) !important;
    border-color: rgba(56, 189, 248, 0.4) !important;
}

section[data-testid="stSidebar"] div[role="radiogroup"] label[data-checked="true"],
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: rgba(56, 189, 248, 0.12) !important;
    border-color: #38bdf8 !important;
}

/* Sidebar Buttons Styling (45 RealEstate, 05 MonthlyReview 표준 일치) */
section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"] {
    gap: 6px !important;
}

section[data-testid="stSidebar"] div.stButton > button {
    border-radius: 6px !important;
    font-weight: 700 !important;
    padding-left: 2px !important;
    padding-right: 2px !important;
    padding-top: 4px !important;
    padding-bottom: 4px !important;
    min-height: 36px !important;
    height: 36px !important;
    white-space: nowrap !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}

section[data-testid="stSidebar"] div.stButton > button p {
    white-space: nowrap !important;
    overflow: visible !important;
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    line-height: 1 !important;
    margin: 0 !important;
    padding: 0 !important;
    display: inline-block !important;
}

/* Sidebar Primary Button (조회 버튼 - 39 DividendStock 표준 스타일 일치) */
section[data-testid="stSidebar"] button[kind="primary"],
.stButton button[kind="primary"] {
    background-color: #2563eb !important;
    color: #ffffff !important;
    border: none !important;
    font-weight: 600 !important;
    font-size: 14.5px !important;
    padding: 8px 16px !important;
    border-radius: 6px !important;
    transition: all 0.2s ease !important;
}

section[data-testid="stSidebar"] button[kind="primary"]:hover,
.stButton button[kind="primary"]:hover {
    background-color: #1d4ed8 !important;
    box-shadow: 0 0 10px rgba(37, 99, 235, 0.4) !important;
}

/* 다운로드 버튼 공통 통일 스타일 */
div[data-testid="stDownloadButton"] > button,
.stDownloadButton > button {
    background-color: #334155 !important;
    color: #f8fafc !important;
    border: 1px solid #475569 !important;
    border-radius: 6px !important;
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    height: 38px !important;
    min-height: 38px !important;
    max-height: 38px !important;
    line-height: 36px !important;
    padding: 0 16px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    text-align: center !important;
    transition: all 0.2s ease-in-out !important;
    box-sizing: border-box !important;
}
div[data-testid="stDownloadButton"] > button:hover,
.stDownloadButton > button:hover {
    background-color: #475569 !important;
    border-color: #38bdf8 !important;
    color: #ffffff !important;
    box-shadow: 0 0 10px rgba(56, 189, 248, 0.25) !important;
}
div[data-testid="stDownloadButton"] > button:active,
.stDownloadButton > button:active {
    background-color: #1e293b !important;
    border-color: #0284c7 !important;
}
div[data-testid="stDownloadButton"] > button p,
div[data-testid="stDownloadButton"] > button span,
.stDownloadButton > button p,
.stDownloadButton > button span {
    font-size: 0.875rem !important;
    font-weight: 500 !important;
    color: inherit !important;
    line-height: inherit !important;
    margin: 0 !important;
    padding: 0 !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Data fetching with Streamlit caching (3 minutes TTL)
@st.cache_data(ttl=180)
def get_cached_market_data(cache_token=0):
    wait = (cache_token > 0)
    return fetch_all_market_data(force_refresh=wait, wait_for_krx=wait), datetime.now(KST)

# Token to allow explicit cache invalidation
if "cache_token" not in st.session_state:
    st.session_state.cache_token = 0

# Fetch Data with spinner when actively refreshing
if st.session_state.cache_token > 0 and st.session_state.get("refreshing", False):
    with st.spinner("최신 시장 데이터 갱신 중..."):
        all_data, fetch_time = get_cached_market_data(st.session_state.cache_token)
    st.session_state["refreshing"] = False
else:
    all_data, fetch_time = get_cached_market_data(st.session_state.cache_token)

# Show toast if just refreshed
if st.session_state.pop("just_refreshed", False):
    st.toast("최신 시장 데이터로 갱신되었습니다.", icon="✅")

# Session state for sector selection
# Session state for sector selection
SECTOR_OPTIONS = ["미국 시장 (US)", "한국 시장 (KRX)", "반도체 섹터 (Semi)"]
legacy_sector_map = {
    "US Market": "미국 시장 (US)",
    "K Market": "한국 시장 (KRX)",
    "Semiconductor": "반도체 섹터 (Semi)"
}

if "selected_sector" not in st.session_state or st.session_state.selected_sector in legacy_sector_map:
    st.session_state.selected_sector = legacy_sector_map.get(st.session_state.get("selected_sector"), "미국 시장 (US)")
if "active_sector" not in st.session_state or st.session_state.active_sector in legacy_sector_map:
    st.session_state.active_sector = legacy_sector_map.get(st.session_state.get("active_sector"), "미국 시장 (US)")

# Sidebar: Market and Sector Selection
with st.sidebar:
    st.markdown(
        """
        <div style='padding: 2px 0 14px 0;'>
            <div style='font-size: 1.25rem; font-weight: 700; color: #f8fafc; letter-spacing: -0.01em; display: flex; align-items: center; gap: 8px;'>
                <span>🏛️</span> 시장/섹터 선택
            </div>
            <div style='font-size: 0.82rem; color: #94a3b8; margin-top: 4px;'>
                조회할 글로벌 시장 또는 섹터를 선택하세요.
            </div>
        </div>
        <hr style='border: 0; height: 1px; background-color: #334155; margin: 12px 0 16px 0;'>
        """,
        unsafe_allow_html=True
    )

    current_idx = SECTOR_OPTIONS.index(st.session_state.selected_sector) if st.session_state.selected_sector in SECTOR_OPTIONS else 0

    chosen_sector = st.radio(
        "🏛️ 시장/섹터 선택",
        options=SECTOR_OPTIONS,
        index=current_idx,
        key="sector_radio_select",
        label_visibility="collapsed"
    )
    st.session_state.selected_sector = chosen_sector

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # Update & 조회 버튼 (45 RealEstate, 05 MonthlyReview 레이아웃 통일)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🔄 Update", use_container_width=True, help="캐시를 초기화하고 최신 시장 데이터를 다시 수집합니다."):
            st.cache_data.clear()
            st.session_state.cache_token += 1
            st.session_state.active_sector = chosen_sector
            st.session_state["just_refreshed"] = True
            st.session_state["refreshing"] = True
            st.rerun()

    with col_btn2:
        if st.button("🔍 조회", type="primary", use_container_width=True, help="선택한 시장 및 섹터로 대시보드를 조회합니다."):
            st.session_state.active_sector = chosen_sector
            st.rerun()

# Centered Title, Dynamic Subtitle (Selected Sector) with KST Updated Time
active_sector = st.session_state.active_sector

market_note = ""
if "US" in active_sector or "미국" in active_sector or active_sector == "US Market":
    market_note = (
        '<div style="text-align: center; font-size: 12.5px; color: #94a3b8; margin-top: 4px;">'
        '* 미국 주식 정규장(22:30~05:00 KST) 개장 전에는 직전 영업일 공식 마감 종가가 표시됩니다. (선물·국채·유가·VIX는 실시간 반영)'
        '</div>'
    )
elif "Semi" in active_sector or "반도체" in active_sector or active_sector == "Semiconductor":
    market_note = (
        '<div style="text-align: center; font-size: 12.5px; color: #94a3b8; margin-top: 4px;">'
        '* 국내 반도체 종목은 당일 정규장 마감 가격이며, 미국 반도체 종목은 개장 전 직전 영업일 종가 기준입니다.'
        '</div>'
    )

st.markdown(
    f'<div style="text-align: center; margin-top: -15px; margin-bottom: 8px;">'
    f'<h1 class="main-title" style="text-align: center; font-size: 2.0rem; font-weight: 800; margin: 0 0 6px 0; color: #8AB4F8 !important; -webkit-text-fill-color: #8AB4F8 !important; letter-spacing: -0.02em;">'
    f'Daily Market Overview'
    f'</h1>'
    f'<div style="text-align: center; font-size: 16px; margin: 0; display: flex; align-items: center; justify-content: center; gap: 8px;">'
    f'<span style="color: #f1f5f9; font-weight: 600; font-size: 16px;">{active_sector}</span>'
    f'<span style="font-size: 16px; color: #cbd5e1; font-weight: 500;">(Updated: {fetch_time.strftime("%Y-%m-%d %H:%M:%S")} KST)</span>'
    f'</div>'
    f'{market_note}'
    f'</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<hr style="border: 0; height: 1px; background-color: #334155; margin: 14px 0 18px 0;">',
    unsafe_allow_html=True
)

def build_tab_cards(ticker_list):
    items_with_index = []
    for idx, ticker in enumerate(ticker_list, start=1):
        item = all_data.get(ticker)
        if item:
            items_with_index.append((item, idx))
        else:
            # Placeholder for missing ticker
            items_with_index.append(({
                "ticker": ticker,
                "name": ticker,
                "price": None,
                "change_amt": None,
                "change_percent": None,
                "history": [],
                "open": None, "high": None, "low": None, "close": None,
                "negative_favorable": False,
                "is_integer_only": False,
                "is_percent": False
            }, idx))
    return render_card_grid(items_with_index)

# Render cards according to active_sector
active_sector = st.session_state.active_sector

if "US" in active_sector or "미국" in active_sector or active_sector == "US Market":
    target_tickers = US_MARKET_TICKERS
elif "KRX" in active_sector or "한국" in active_sector or active_sector == "K Market":
    target_tickers = K_MARKET_TICKERS
else:
    target_tickers = SEMI_MARKET_TICKERS

cards_html = build_tab_cards(target_tickers)
st.markdown(cards_html, unsafe_allow_html=True)

# Bottom Horizontal Divider
st.markdown(
    '<hr style="border: 0; height: 1px; background-color: #334155; margin: 24px 0 28px 0;">'
    "<div style='text-align: center; color: #64748b; font-size: 0.8rem; margin-top: 8px; margin-bottom: 24px; line-height: 1.6;'>"
    "⚠️ 본 서비스에서 제공하는 모든 정보는 투자 참고용이며, 투자의 최종 결정과 책임은 투자자 본인에게 있습니다."
    "</div>",
    unsafe_allow_html=True
)

