import math, io, time
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="AI 뉴스리포트 – 실시간 티커바", layout="wide")

# -------- 포맷 ----------
def fmt_num(x, d=2):
    if x is None: return "—"
    try:
        if math.isnan(x) or math.isinf(x): return "—"
    except Exception: pass
    return f"{x:,.{d}f}"

def fmt_pct(x):
    if x is None: return "—"
    try:
        if math.isnan(x) or math.isinf(x): return "—"
    except Exception: pass
    return f"{x:+.2f}%"

def klass_of(delta):
    if delta is None: return "flat"
    if delta > 0: return "up"
    if delta < 0: return "down"
    return "flat"

# -------- 데이터 소스 ----------
STOOQ_MAP = {
    "^KS11": "^ks11", "^KQ11": "^kq11", "^DJI": "^dji", "^IXIC": "^ixic",
    "KRW=X": "usdkrw", "CL=F": "cl.f", "GC=F": "gc.f", "HG=F": "hg.f",
}

@st.cache_data(ttl=600)
def fetch_stooq(symbol: str):
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
def fetch_yahoo(symbol: str):
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote_plus(symbol)}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        j = r.json().get("quoteResponse", {}).get("result", [])
        if not j: return None, None, None
        d = j[0]
        return float(d.get("regularMarketPrice")), float(d.get("regularMarketPreviousClose")), "yahoo"
    except Exception:
        return None, None, None

def get_quote(symbol: str):
    last, prev, src = fetch_stooq(symbol)
    if last and not prev:
        _, prev_y, _ = fetch_yahoo(symbol)
        prev = prev_y
    if last and prev: return last, prev, src
    return fetch_yahoo(symbol)

# -------- 대상 티커 ----------
ITEMS = [
    ("KOSPI", "^KS11"),
    ("KOSDAQ", "^KQ11"),
    ("DOW", "^DJI"),
    ("NASDAQ", "^IXIC"),
    ("USD/KRW", "KRW=X"),
    ("WTI", "CL=F"),
    ("Gold", "GC=F"),
    ("Copper", "HG=F"),
]

# -------- 스타일 ----------
st.markdown("""
<style>
body { background:#0f131a; color:#d1d5db; }
.panel { display:flex; gap:.75rem; align-items:center; margin-bottom:.5rem; }
.small { color:#9aa3ad; font-size:.9rem; }

.ticker-wrap {
  border:1px solid #1f2937; border-radius:12px; background:#0f131a;
  overflow:hidden; white-space:nowrap; padding:8px 0; position:relative;
}
.ticker {
  display:inline-block; padding-right:60px;
  animation: scroll-left VAR_SPEED linear infinite;
}
.ticker-wrap:hover .ticker { animation-play-state: paused; }  /* hover to pause */

.item { padding: 0 18px; }
.up { color:#e05246; font-weight:600; }
.down { color:#2a7be6; font-weight:600; }
.flat { color:#9aa3ad; font-weight:600; }

@keyframes scroll-left {
  0% { transform:translateX(100%); }
  100% { transform:translateX(-100%); }
}
</style>
""".replace("VAR_SPEED", "40s"), unsafe_allow_html=True)

# -------- 상단 컨트롤 ----------
left, mid, right = st.columns([1,1,2])
with left:
    speed = st.slider("스크롤 속도(초, 작을수록 빠름)", 10, 90, 40, step=5)
with mid:
    refresh = st.button("🔄 새로고침")
with right:
    kst = ZoneInfo("Asia/Seoul")
    st.markdown(f"<div class='small' style='text-align:right'>업데이트: {datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S (KST)')}</div>", unsafe_allow_html=True)

# 속도 반영
st.markdown(f"<style>.ticker{{animation-duration:{speed}s;}}</style>", unsafe_allow_html=True)

# 버튼 누르면 캐시 클리어
if refresh:
    fetch_stooq.clear()
    fetch_yahoo.clear()
    st.experimental_rerun()

# -------- 데이터 구성 & 렌더 ----------
parts = []
for name, sym in ITEMS:
    last, prev, _src = get_quote(sym)
    delta = pct = None
    if last and prev:
        delta = last - prev
        pct = (delta / prev) * 100
    klass = klass_of(delta)
    arrow = "▲" if klass == "up" else "▼" if klass == "down" else "–"
    parts.append(f"<span class='item {klass}'>{name} {fmt_num(last)} {arrow}{fmt_pct(pct)}</span>")

html = "｜".join(parts)
st.markdown(f"""
<div class="ticker-wrap">
  <div class="ticker">{html}</div>
</div>
""", unsafe_allow_html=True)

st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Stooq → Yahoo Finance (10분 캐시)")
