import math
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import pandas as pd
import requests
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
# ① Stooq CSV → ② Yahoo HTTP → ③ yfinance (모두 10분 캐시)
# ──────────────────────────────────────────────────────────────────────────────
STOOQ_MAP = {
    # 지수
    "^KS11": "^ks11",   # KOSPI
    "^KQ11": "^kq11",   # KOSDAQ
    "^DJI":  "^dji",    # 다우
    "^IXIC": "^ixic",   # 나스닥
    # 환율/원자재
    "KRW=X": "usdkrw",  # USD/KRW (stooq는 거꾸로 표기지만 호가가 USDKRW를 그대로 반환)
    "CL=F":  "cl.f",    # WTI
    "GC=F":  "gc.f",    # Gold
    "HG=F":  "hg.f",    # Copper
}

@st.cache_data(ttl=600)
def fetch_quote_stooq(symbol: str):
    sym = STOOQ_MAP.get(symbol)
    if not sym:
        return None, None, None
    url = f"https://stooq.com/q/l/?s={quote_plus(sym)}&f=sd2t2ohlcv&h&e=csv"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(pd.compat.StringIO(r.text))
        if df.empty:
            return None, None, None
        # Stooq CSV: columns = Symbol,Date,Time,Open,High,Low,Close,Volume
        last = float(df.loc[0, "Close"])
        # 이전 종가는 한 줄 CSV라서 바로 못 줌 → 야후 HTTP로 보조, 없으면 None
        return last, None, "stooq"
    except Exception:
        return None, None, None

@st.cache_data(ttl=600)
def fetch_quote_http(symbol: str):
    """Yahoo v7 quote API"""
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote_plus(symbol)}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json().get("quoteResponse", {}).get("result", [])
        if not data:
            return None, None, None
        d = data[0]
        last = d.get("regularMarketPrice")
        prev = d.get("regularMarketPreviousClose")
        if last is not None and prev is not None:
            return float(last), float(prev), "yahoo_http"
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=600)
def fetch_quote_yf(symbol: str):
    try:
        df = yf.download(symbol, period="7d", interval="1d", progress=False, auto_adjust=False)
        closes = df.get("Close")
        if closes is None or closes.dropna().empty:
            return None, None, None
        closes = closes.dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev, "yfinance"
    except Exception:
        return None, None, None

def fetch_quote(symbol: str):
    # 1) Stooq(빠름/안정) 시도
    last, prev, src = fetch_quote_stooq(symbol)
    # Stooq는 prev가 없으니, 있으면 OK, 없으면 보조로 Yahoo HTTP
    if last is not None and prev is None:
        _, prev_http, _ = fetch_quote_http(symbol)
        if prev_http is not None:
            prev = prev_http
    if last is not None and prev is not None:
        return last, prev, src

    # 2) Yahoo HTTP
    last, prev, src = fetch_quote_http(symbol)
    if last is not None and prev is not None:
        return last, prev, src

    # 3) yfinance
    last, prev, src = fetch_quote_yf(symbol)
    return last, prev, src

# ──────────────────────────────────────────────────────────────────────────────
# UI (컴팩트)
# ──────────────────────────────────────────────────────────────────────────────
CARD_CSS = """
<style>
.kpi-wrap { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:10px; }
@media (max-width:1100px){ .kpi-wrap{ grid-template-columns: repeat(2, minmax(0,1fr)); } }
@media (max-width:640px){ .kpi-wrap{ grid-template-columns: repeat(1, minmax(0,1fr)); } }

.kpi-card { background:#111418; border:1px solid #1f2937; border-radius:10px; padding:8px 10px; }
.kpi-title{ font-size:.85rem; color:#a3aab8; margin-bottom:2px; line-height:1.05; }
.kpi-value{ font-size:1.15rem; font-weight:800; letter-spacing:-0.01em; }
.kpi-delta{ font-size:.85rem; margin-top:2px; }
.kpi-up   { color:#d93025; }   /* 빨강 */
.kpi-down { color:#1a73e8; }   /* 파랑 */
.kpi-flat { color:#9aa0a6; }
.kpi-src  { font-size:.70rem; color:#7c8293; margin-top:2px; }
</style>
"""
st.markdown(CARD_CSS, unsafe_allow_html=True)

def render_card(title: str, last: float, prev: float, value_fmt="auto", source=None):
    delta = None
    pct = None
    if last is not None and prev not in (None, 0):
        try:
            delta = last - prev
            pct = (delta / prev) * 100
        except Exception:
            delta, pct = None, None

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

    src_text = f'<div class="kpi-src">{source or "-"}</div>'

    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-title">{title}</div>
          <div class="kpi-value">{value_text}</div>
          <div class="kpi-delta {klass}">{delta_text}</div>
          {src_text}
        </div>
        """,
        unsafe_allow_html=True,
    )

# ──────────────────────────────────────────────────────────────────────────────
# 심볼 정의
# ──────────────────────────────────────────────────────────────────────────────
INDEXES = [
    ("KOSPI",   "^KS11",  "auto"),
    ("KOSDAQ",  "^KQ11",  "auto"),
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
# 렌더링
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("## 🧠 AI 뉴스리포트 – 상단 요약")
kst = ZoneInfo("Asia/Seoul")
st.caption(f"업데이트: {datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S (KST)')}")
st.markdown("### 📉 오늘의 시장 요약")

st.markdown('<div class="kpi-wrap">', unsafe_allow_html=True)
# 지수
for name, sym, vfmt in INDEXES:
    last, prev, src = fetch_quote(sym)
    render_card(name, last, prev, vfmt, source=src)
# 환율/원자재
for name, sym, vfmt in OTHERS:
    last, prev, src = fetch_quote(sym)
    render_card(name, last, prev, vfmt, source=src)
st.markdown('</div>', unsafe_allow_html=True)

st.caption("※ 상승=빨강, 하락=파랑 · 데이터 우선순위: Stooq → Yahoo → yfinance")
