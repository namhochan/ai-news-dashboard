import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

# -----------------------------
# 기본 페이지 설정
# -----------------------------
st.set_page_config(
    page_title="AI 뉴스리포트 – 상단 요약",
    layout="wide",
)

# -----------------------------
# 유틸: 숫자 포맷
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
# 시세 가져오기 (안정형)
# -----------------------------
def fetch_quote(ticker: str):
    """
    1) fast_info 시도
    2) 실패 시 7일 history에서 마지막 두 종가 사용
    """
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass

    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        if df.empty:
            return None, None
        closes = df["Close"].dropna()
        if len(closes) == 0:
            return None, None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# -----------------------------
# 카드 UI (상승=빨강, 하락=파랑)
# -----------------------------
CARD_CSS = """
<style>
.kpi-grid   { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.kpi-card   { border-radius: 14px; padding: 14px 16px; background: #111418; border: 1px solid #1f2937; }
.kpi-title  { font-size: 0.95rem; color: #a3aab8; margin-bottom: 6px; }
.kpi-value  { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }
.kpi-delta  { font-size: 0.95rem; margin-top: 6px; }
.kpi-up     { color: #d93025; } /* 빨강 */
.kpi-down   { color: #1a73e8; } /* 파랑 */
.kpi-flat   { color: #9aa0a6; } /* 보조 */
.small      { font-size: 0.85rem; color:#8b93a7;}
@media (max-width: 1000px) { .kpi-grid { grid-template-columns: repeat(2, 1fr); } }
</style>
"""
st.markdown(CARD_CSS, unsafe_allow_html=True)

def render_card(title: str, last: float, prev: float, value_fmt="auto"):
    delta = None
    pct = None
    if last is not None and prev not in (None, 0):
        delta = last - prev
        pct = (delta / prev) * 100

    if delta is None or math.isfinite(delta) is False:
        klass = "kpi-flat"
    elif delta > 0:
        klass = "kpi-up"
    elif delta < 0:
        klass = "kpi-down"
    else:
        klass = "kpi-flat"

    if value_fmt == "krw":
        value_text = fmt_number(last, 2)
        delta_text = f"{fmt_number(delta, 2)}  ({fmt_percent(pct)})" if delta is not None else "-"
    elif value_fmt == "3dp":
        value_text = fmt_number(last, 3)
        delta_text = f"{fmt_number(delta, 3)}  ({fmt_percent(pct)})" if delta is not None else "-"
    else:
        value_text = fmt_number(last, 2)
        delta_text = f"{fmt_number(delta, 2)}  ({fmt_percent(pct)})" if delta is not None else "-"

    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-title">{title}</div>
      <div class="kpi-value">{value_text}</div>
      <div class="kpi-delta {klass}">{delta_text}</div>
    </div>
    """, unsafe_allow_html=True)

# -----------------------------
# 대상 심볼
# -----------------------------
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

# -----------------------------
# 헤더/시간
# -----------------------------
st.markdown("## 🧠 AI 뉴스리포트 – 상단 요약")
kst = ZoneInfo("Asia/Seoul")
now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S (KST)")
st.caption(f"업데이트: {now_str}")
st.markdown("### 📈 오늘의 시장 요약")

# -----------------------------
# 행1: 지수
# -----------------------------
st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)
for (name, ticker, fmt) in INDEXES:
    last, prev = fetch_quote(ticker)
    render_card(name, last, prev, fmt)
st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------
# 행2: 환율/원자재
# -----------------------------
st.markdown('<div class="kpi-grid" style="margin-top:10px;">', unsafe_allow_html=True)
for (name, ticker, fmt) in OTHERS:
    last, prev = fetch_quote(ticker)
    render_card(name, last, prev, fmt)
st.markdown('</div>', unsafe_allow_html=True)

st.divider()
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (yfinance)")
