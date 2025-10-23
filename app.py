import math
import io  # ★ 중요: StringIO는 pandas.compat가 아니라 io에서 가져오기
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="AI 뉴스리포트 – 상단 요약(원카드)", layout="wide")

CSS = """
<style>
.card{background:#101318;border:1px solid #1f2533;border-radius:14px;padding:12px 14px}
.card h3{margin:0 0 8px 0;font-size:1.05rem}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 12px}
.row{display:flex;align-items:center;justify-content:space-between;background:#0c0f14;
     padding:8px 10px;border:1px solid #1b2230;border-radius:10px}
.name{font-size:.92rem;color:#a7b0c2}
.valbox{display:flex;gap:10px;align-items:baseline}
.value{font-weight:800;font-size:1.06rem;letter-spacing:-.01em}
.delta{font-size:.88rem}
.up{color:#e05246}.down{color:#2a7be6}.flat{color:#9aa3ad}
.src{font-size:.72rem;color:#788196;margin-top:8px}
@media (max-width:860px){.grid{grid-template-columns:1fr}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

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

STOOQ_MAP = {
    "^KS11": "^ks11",  # KOSPI
    "^KQ11": "^kq11",  # KOSDAQ
    "^DJI" : "^dji",   # DOW
    "^IXIC": "^ixic",  # NASDAQ
    "KRW=X": "usdkrw", # USD/KRW
    "CL=F" : "cl.f",   # WTI
    "GC=F" : "gc.f",   # Gold
    "HG=F" : "hg.f",   # Copper
}

@st.cache_data(ttl=600)
def fetch_stooq(symbol:str):
    s = STOOQ_MAP.get(symbol)
    if not s: 
        return None, None, None
    url = f"https://stooq.com/q/l/?s={quote_plus(s)}&f=sd2t2ohlcv&h&e=csv"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        # ★ pandas.compat.StringIO(X) → io.StringIO(O)
        df = pd.read_csv(io.StringIO(r.text))
        if df.empty: return None, None, None
        last = float(df.loc[0, "Close"])
        # Stooq 라이트 CSV엔 이전종가가 없어 보강 필요
        return last, None, "stooq"
    except Exception:
        return None, None, None

@st.cache_data(ttl=600)
def fetch_yahoo_http(symbol:str):
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={quote_plus(symbol)}"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        j = r.json().get("quoteResponse", {}).get("result", [])
        if not j: return None, None, None
        d = j[0]
        last = d.get("regularMarketPrice")
        prev = d.get("regularMarketPreviousClose")
        if last is not None and prev is not None:
            return float(last), float(prev), "yahoo_http"
    except Exception:
        pass
    return None, None, None

@st.cache_data(ttl=600)
def fetch_yf(symbol:str):
    try:
        df = yf.download(symbol, period="7d", interval="1d", progress=False, auto_adjust=False)
        c = df.get("Close")
        if c is None or c.dropna().empty: return None, None, None
        c = c.dropna()
        last = float(c.iloc[-1])
        prev = float(c.iloc[-2]) if len(c) >= 2 else None
        return last, prev, "yfinance"
    except Exception:
        return None, None, None

def get_quote(symbol:str):
    # 1) Stooq (last) → prev는 Yahoo HTTP로 보강
    last, prev, src = fetch_stooq(symbol)
    if last is not None and prev is None:
        _, prev2, _ = fetch_yahoo_http(symbol)
        if prev2 is not None: prev = prev2
    if last is not None and prev is not None:
        return last, prev, src

    # 2) Yahoo HTTP
    last, prev, src = fetch_yahoo_http(symbol)
    if last is not None and prev is not None:
        return last, prev, src

    # 3) yfinance
    last, prev, src = fetch_yf(symbol)
    return last, prev, src

ITEMS = [
    ("KOSPI",   "^KS11",  "auto"),
    ("KOSDAQ",  "^KQ11",  "auto"),
    ("DOW",     "^DJI",   "auto"),
    ("NASDAQ",  "^IXIC",  "auto"),
    ("USD/KRW", "KRW=X",  "krw"),
    ("WTI",     "CL=F",   "auto"),
    ("Gold",    "GC=F",   "auto"),
    ("Copper",  "HG=F",   "3dp"),
]

st.markdown("## 🧠 AI 뉴스리포트 – 상단 요약 (원카드)")
kst = ZoneInfo("Asia/Seoul")
st.caption(f"업데이트: {datetime.now(kst).strftime('%Y-%m-%d %H:%M:%S (KST)')}")

with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("<h3>📊 오늘의 시장 요약</h3>", unsafe_allow_html=True)
    st.markdown('<div class="grid">', unsafe_allow_html=True)

    debug_rows = []
    for name, sym, vfmt in ITEMS:
        last, prev, src = get_quote(sym)

        delta = pct = None
        if last is not None and prev not in (None, 0):
            try:
                delta = last - prev
                pct = (delta / prev) * 100
            except Exception:
                pass

        klass = classify(delta)
        if vfmt == "krw":
            vtxt = fmt_num(last, 2)
            dtxt = f"{fmt_num(delta,2)} ({fmt_pct(pct)})" if delta is not None else "-"
        elif vfmt == "3dp":
            vtxt = fmt_num(last, 3)
            dtxt = f"{fmt_num(delta,3)} ({fmt_pct(pct)})" if delta is not None else "-"
        else:
            vtxt = fmt_num(last, 2)
            dtxt = f"{fmt_num(delta,2)} ({fmt_pct(pct)})" if delta is not None else "-"

        st.markdown(f"""
        <div class="row">
          <div class="name">{name}</div>
          <div class="valbox">
            <div class="value">{vtxt}</div>
            <div class="delta {klass}">{dtxt}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        debug_rows.append(
            {"name": name, "symbol": sym, "last": last, "prev": prev, "delta": delta, "pct": pct, "source": src}
        )

    st.markdown('</div>', unsafe_allow_html=True)  # grid
    st.markdown('<div class="src">※ 상승=빨강, 하락=파랑 · 데이터 소스: Stooq → Yahoo → yfinance (10분 캐시)</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # card

with st.expander("🔧 디버그(수집결과 확인)"):
    st.dataframe(pd.DataFrame(debug_rows))
