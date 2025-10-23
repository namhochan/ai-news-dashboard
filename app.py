import math
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import requests
import pandas as pd
import streamlit as st
import yfinance as yf

# ──────────────────────────────────────────────────────────────────────────────
# 기본 설정
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI 뉴스리포트 – 상단 요약", layout="wide")

# ──────────────────────────────────────────────────────────────────────────────
# 유틸
# ──────────────────────────────────────────────────────────────────────────────
def fmt_number(val: float, decimals: int = 2) -> str:
    if val is None:
        return "-"
    try:
        if math.isnan(val) or math.isinf(val):
            return "-"
    except Exception:
        pass
    return f"{val:,.{decimals}f}"

def fmt_percent(pct: float) -> str:
    if pct is None:
        return "-"
    try:
        if math.isnan(pct) or math.isinf(pct):
            return "-"
    except Exception:
        pass
    return f"{pct:+.2f}%"

# ──────────────────────────────────────────────────────────────────────────────
# 시세 가져오기: Yahoo HTTP → yfinance 백업 (캐시 10분)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def fetch_quote_http(symbol: str):
    """Yahoo finance quote API (빠르고 안정적)"""
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote_plus(symbol)}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("quoteResponse", {}).get("result", [])
        if not data:
            return None, None
        d = data[0]
        last = d.get("regularMarketPrice")
        prev = d.get("regularMarketPreviousClose")
        if last is not None and prev is not None:
            return float(last), float(prev)
    except Exception:
        pass
    return None, None

@st.cache_data(ttl=600)
def fetch_quote_yf(symbol: str):
    """백업: yfinance history 7일"""
    try:
        df = yf.download(symbol, period="7d", interval="1d", progress=False, auto_adjust=False)
        closes = df.get("Close")
        if closes is None or closes.dropna().empty:
            return None, None
        closes = closes.dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

def fetch_quote(symbol: str):
    last, prev = fetch_quote_http(symbol)
    if last is None or prev is None:
        last, prev = fetch_quote_yf(symbol)
    return last, prev

# ──────────────────────────────────────────────────────────────────────────────
# 카드 UI (컴팩트·반응형, 상승=빨강 / 하락=파랑)
# ──────────────────────────────────────────────────────────────────────────────
CARD_CSS = """
<style>
.kpi-wrap { display:grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap:12px; }
@media (max-width:1100px){ .kpi-wrap{ grid-template-columns: repeat(2, minmax(0,1fr)); } }
@media (max-width:640px){ .kpi-wrap{ grid-template-columns: repeat(1, minmax(0,1fr)); } }

.kpi-card { background:#111418; border:1px solid #1f2937; border-radius:12px; padding:10px 12px; }
.kpi-title{ font-size:.9rem; color:#a3aab8; line-height:1.1; margin-bottom:4px; }
.kpi-value{ font-size:1.3rem; font-weight:800; letter-spacing:-0.01em; }
.kpi-delta{ font-size:.9rem; margin-top:4px; }
.kpi-up   { color:#d93025; }   /* 빨강 */
.kpi-down { color:#1a73e8; }   /* 파랑 */
.kpi-flat { color:#9aa0a6; }
</style>
"""
st.markdown(CARD_CSS, unsafe_allow_html=True)

def render_card(title: str, last: float, prev: float, value_fmt="auto"):
    delta = None
    pct = None
    if last is not None and prev not in (None, 0):
        delta = last - prev
        try:
            pct = (delta / prev) * 100 if prev else None
        except Exception:
            pct = None

    if delta is None:
        klass = "kpi-flat"
    elif delta > 0:
        klass = "kpi-up"
    elif delta < 0:
        klass = "kpi-down"
    else:
        klass = "kpi-flat"

    if value_fmt == "krw":
        value_text = fmt_number(last, 2)
        delta_text = f"{fmt_number(delta, 2)} ({fmt_percent(pct)})" if delta is not None else "-"
    elif value_fmt == "3dp":
        value_text = fmt_number(last, 3)
        delta_text = f"{fmt_number(delta, 3)} ({fmt_percent(pct)})" if delta is not None else "-"
    else:
        value_text = fmt_number(last, 2)
        delta_text = f"{fmt_number(delta, 2)} ({fmt_percent(pct)})" if delta is not None else "-"

    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-title">{title}</div>
          <div class="kpi-value">{value_text}</div>
          <div class="kpi-delta {klass}">{delta_text}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# 대상 심볼
# ──────────────────────────────────────────────────────────────────────────────
INDEXES = [
    ("KOSPI",   "^KS11",  "auto"),
    ("KOSDAQ",  "^KQ11",  "auto"),   # KOSDAQ Composite
    ("DOW",     "^DJI",   "auto"),
    ("NASDAQ",  "^IXIC",  "auto"),
]
OTHERS = [
    ("USD/KRW", "KRW=X",  "krw"),
    ("WTI",     "CL=F",   "auto"),
    ("Gold",    "GC=F",   "auto"),
    ("Copper",  "HG=F",   "3dp"),
]

# ──────────────────────────────────────────────────────────────────────────────
# 헤더 및 시간
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("## 🧠 AI 뉴스리포트 – 상단 요약")
kst = ZoneInfo("Asia/Seoul")
st.caption(f"업데이트: {datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S (KST)')}")
st.markdown("### 📈 오늘의 시장 요약")

# ──────────────────────────────────────────────────────────────────────────────
# 지수/환율/원자재 카드 렌더링
# ──────────────────────────────────────────────────────────────────────────────
st.markdown('<div class="kpi-wrap">', unsafe_allow_html=True)
for title, symbol, vfmt in INDEXES:
    last, prev = fetch_quote(symbol)
    render_card(title, last, prev, vfmt)
for title, symbol, vfmt in OTHERS:
    last, prev = fetch_quote(symbol)
    render_card(title, last, prev, vfmt)
st.markdown('</div>', unsafe_allow_html=True)

st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance")
