import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="AI 뉴스리포트 – 실시간 지수 티커바",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -----------------------------
# 숫자 포맷
# -----------------------------
def fmt_number(val: float, decimals: int = 2) -> str:
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "-"
    return f"{val:,.{decimals}f}"

def fmt_percent(pct: float) -> str:
    if pct is None or (isinstance(pct, float) and (math.isnan(pct) or math.isinf(pct))):
        return "-"
    return f"{pct:+.2f}%"

# -----------------------------
# 시세 가져오기 (yfinance + fallback)
# -----------------------------
@st.cache_data(ttl=600)
def fetch_quote(ticker: str):
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
        closes = df["Close"].dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# -----------------------------
# 티커 데이터 구성
# -----------------------------
INDEXES = [
    ("KOSPI", "^KS11"),
    ("KOSDAQ", "^KQ11"),
    ("DOW", "^DJI"),
    ("NASDAQ", "^IXIC"),
    ("USD/KRW", "KRW=X"),
    ("WTI", "CL=F"),
    ("Gold", "GC=F"),
    ("Copper", "HG=F"),
]

# -----------------------------
# 상단 제목
# -----------------------------
st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
kst = ZoneInfo("Asia/Seoul")
now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S (KST)")
st.caption(f"업데이트: {now_str}")

# -----------------------------
# 새로고침 버튼
# -----------------------------
col1, col2 = st.columns([5, 1])
with col1:
    st.markdown("### 📈 오늘의 시장 요약")
with col2:
    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

# -----------------------------
# 티커바 생성
# -----------------------------
ticker_data = []
for name, code in INDEXES:
    last, prev = fetch_quote(code)
    if last and prev:
        diff = last - prev
        pct = (diff / prev) * 100 if prev != 0 else 0
        arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "–")
        color = "red" if diff > 0 else ("#1a73e8" if diff < 0 else "#999")
        text = f"<span style='color:{color}; font-weight:bold'>{name} {fmt_number(last)} {arrow} {fmt_percent(pct)}</span>"
        ticker_data.append(text)

ticker_html = " &nbsp; | &nbsp; ".join(ticker_data)

# -----------------------------
# CSS 티커 효과
# -----------------------------
TICKER_CSS = """
<style>
.ticker-wrap {
  width: 100%%;
  overflow: hidden;
  background: #111418;
  border-radius: 8px;
  border: 1px solid #222;
  padding: 6px 0;
}
.ticker {
  display: inline-block;
  white-space: nowrap;
  animation: scroll-left linear infinite;
  animation-duration: 50s;
  font-size: 1.1rem;
}
@keyframes scroll-left {
  from { transform: translateX(100%%); }
  to { transform: translateX(-100%%); }
}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)
st.markdown(f"<div class='ticker-wrap'><div class='ticker'>{ticker_html}</div></div>", unsafe_allow_html=True)

st.caption("※ 상승=빨강 · 하락=파랑 · 데이터: Yahoo Finance (10분 캐시)")
