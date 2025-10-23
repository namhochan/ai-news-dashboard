import math
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

# --------------------------
# 기본 설정
# --------------------------
st.set_page_config(page_title="AI 뉴스리포트 – 실시간 티커바", layout="wide")

# --------------------------
# 포맷 함수
# --------------------------
def fmt_num(x, d=2):
    if x is None: return "-"
    try:
        if math.isnan(x) or math.isinf(x): return "-"
    except Exception: pass
    return f"{x:,.{d}f}"

def fmt_pct(x):
    if x is None: return "-"
    try:
        if math.isnan(x) or math.isinf(x): return "-"
    except Exception: pass
    return f"{x:+.2f}%"

def classify(delta):
    if delta is None: return "flat"
    if delta > 0: return "up"
    if delta < 0: return "down"
    return "flat"

# --------------------------
# 데이터 수집
# --------------------------
STOOQ_MAP = {
    "^KS11": "^ks11", "^KQ11": "^kq11", "^DJI": "^dji", "^IXIC": "^ixic",
    "KRW=X": "usdkrw", "CL=F": "cl.f", "GC=F": "gc.f", "HG=F": "hg.f",
}

@st.cache_data(ttl=600)
def fetch_stooq(symbol):
    s = STOOQ_MAP.get(symbol)
    if not s: return None, None, None
    url = f"https://stooq.com/q/l/?s={quote_plus(s)}&f=sd2t2ohlcv&h&e=csv"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty: return None, None, None
        last = float(df.loc[0, "Close"])
        return last, None, "stooq"
    except Exception:
        return None, None, None

@st.cache_data(ttl=600)
def fetch_yahoo(symbol):
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote_plus(symbol)}"
    try:
        r = requests.get(url, timeout=10)
        j = r.json().get("quoteResponse", {}).get("result", [])
        if not j: return None, None, None
        d = j[0]
        return float(d.get("regularMarketPrice")), float(d.get("regularMarketPreviousClose")), "yahoo"
    except Exception:
        return None, None, None

def get_quote(symbol):
    last, prev, src = fetch_stooq(symbol)
    if last and not prev:
        _, prev2, _ = fetch_yahoo(symbol)
        prev = prev2
    if last and prev: return last, prev, src
    last, prev, src = fetch_yahoo(symbol)
    return last, prev, src

# --------------------------
# 대상 목록
# --------------------------
ITEMS = [
    ("KOSPI", "^KS11"), ("KOSDAQ", "^KQ11"),
    ("DOW", "^DJI"), ("NASDAQ", "^IXIC"),
    ("USD/KRW", "KRW=X"), ("WTI", "CL=F"),
    ("Gold", "GC=F"), ("Copper", "HG=F"),
]

# --------------------------
# 티커 스타일
# --------------------------
st.markdown("""
<style>
body { background:#0f131a; color:#d1d5db; }
.ticker {
  white-space: nowrap;
  overflow: hidden;
  box-sizing: border-box;
  background: #0f131a;
  border: 1px solid #1f2937;
  border-radius: 12px;
  padding: 10px 0;
  font-size: 1rem;
}
.ticker span {
  display: inline-block;
  padding-right: 60px;
  animation: scroll-left 40s linear infinite;
}
@keyframes scroll-left {
  0% { transform: translateX(100%); }
  100% { transform: translateX(-100%); }
}
.up { color: #e05246; font-weight:600; }
.down { color: #2a7be6; font-weight:600; }
.flat { color: #9aa3ad; font-weight:600; }
</style>
""", unsafe_allow_html=True)

# --------------------------
# 데이터 렌더
# --------------------------
kst = ZoneInfo("Asia/Seoul")
st.markdown(f"#### 🧠 AI 뉴스리포트 실시간 티커바 ({datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S')})")

ticker_items = []
for name, sym in ITEMS:
    last, prev, src = get_quote(sym)
    delta = pct = None
    if last and prev:
        delta = last - prev
        pct = (delta / prev) * 100
    klass = classify(delta)
    arrow = "▲" if klass == "up" else "▼" if klass == "down" else "–"
    ptxt = fmt_pct(pct)
    ticker_items.append(f"<span class='{klass}'>{name} {fmt_num(last)} {arrow}{ptxt}</span>")

ticker_html = " ｜ ".join(ticker_items)
st.markdown(f"<div class='ticker'><span>{ticker_html}</span></div>", unsafe_allow_html=True)

st.caption("※ 상승=빨강, 하락=파랑 · 데이터 소스: Stooq → Yahoo Finance (10분 캐시)")
