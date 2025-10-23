# -*- coding: utf-8 -*-
"""
시장 지수 / 환율 / 원자재 데이터 수집 + 티커바 렌더링
"""

import math
import yfinance as yf
import streamlit as st

# ---------------------------------------------------
# 숫자 포맷 유틸
# ---------------------------------------------------
def fmt_number(v, d=2):
    try:
        if v is None or math.isnan(v):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def fmt_percent(v):
    try:
        if v is None or math.isnan(v):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

# ---------------------------------------------------
# 시세 수집 (fast_info → fallback)
# ---------------------------------------------------
@st.cache_data(ttl=300)
def fetch_quote(ticker: str):
    """단일 티커 시세 조회 (종가/전일대비)"""
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False)
        if df.empty:
            return None, None
        close = df["Close"].dropna()
        last = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# ---------------------------------------------------
# 티커 리스트 정의
# ---------------------------------------------------
INDEXES = [
    ("KOSPI", "^KS11", 2),
    ("KOSDAQ", "^KQ11", 2),
    ("DOW", "^DJI", 2),
    ("NASDAQ", "^IXIC", 2),
]
OTHERS = [
    ("USD/KRW", "KRW=X", 2),
    ("WTI", "CL=F", 2),
    ("Gold", "GC=F", 2),
    ("Copper", "HG=F", 3),
]

# ---------------------------------------------------
# 티커바 CSS
# ---------------------------------------------------
TICKER_CSS = """
<style>
.ticker-wrap{
  overflow:hidden;width:100%;
  border:1px solid #263042;
  border-radius:10px;
  background:#0f1420;
  margin-bottom:10px;
}
.ticker-track{
  display:flex;
  gap:14px;
  align-items:center;
  width:max-content;
  will-change:transform;
  animation:ticker-scroll var(--speed,35s) linear infinite;
}
@keyframes ticker-scroll{
  0%{transform:translateX(0);}
  100%{transform:translateX(-50%);}
}
.badge{
  display:inline-flex;
  align-items:center;
  gap:8px;
  background:#0f1420;
  border:1px solid #2b3a55;
  color:#c7d2fe;
  padding:5px 10px;
  border-radius:8px;
  font-weight:600;
  white-space:nowrap;
}
.badge .name{color:#9fb3c8;font-weight:600;}
.badge .up{color:#ff5c5c;}
.badge .down{color:#5ea0ff;}
.sep{color:#44526b;padding:0 6px;}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

# ---------------------------------------------------
# 내부 함수
# ---------------------------------------------------
def _build_ticker_items():
    rows = INDEXES + OTHERS
    items = []
    for name, ticker, dp in rows:
        last, prev = fetch_quote(ticker)
        delta, pct = None, None
        if last and prev:
            delta = last - prev
            pct = (delta / prev) * 100
        items.append({
            "name": name,
            "last": fmt_number(last, dp),
            "pct": fmt_percent(pct),
            "is_up": (delta or 0) > 0,
            "is_down": (delta or 0) < 0,
        })
    return items

# ---------------------------------------------------
# 공개 함수
# ---------------------------------------------------
def render_ticker_line(speed_sec: int = 35):
    """실시간 시장 요약 티커바 렌더링"""
    items = _build_ticker_items()
    chips = []
    for it in items:
        arrow = "▲" if it["is_up"] else ("▼" if it["is_down"] else "■")
        cls = "up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(
            f"<span class='badge'><span class='name'>{it['name']}</span>"
            f"{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>"
        )
    line = "<span class='sep'>|</span>".join(chips)
    html = f"""
    <div class='ticker-wrap' style='--speed:{speed_sec}s'>
      <div class='ticker-track'>
        {line}<span class='sep'>|</span>{line}
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
