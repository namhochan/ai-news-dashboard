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
    page_title="AI 뉴스리포트 – 상단 요약바",
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
    1) fast_info 로 시세/전일종가 시도
    2) 실패 시 history 로 5일치 받아서 마지막 유효 종가와 이전 종가 활용
    """
    try:
        t = yf.Ticker(ticker)
        # 1) fast_info
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass

    # 2) history fallback
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
# 카드 UI
# (한국 관행: 상승=빨강, 하락=파랑)
# -----------------------------
CARD_CSS = """
<style>
.kpi-card {
  border-radius: 14px;
  padding: 14px 16px;
  background: #111418;
  border: 1px solid #1f2937;
}
.kpi-title {
  font-size: 0.95rem;
  color: #a3aab8;
  margin-bottom: 6px;
}
.kpi-value {
  font-size: 1.6rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.kpi-delta {
  font-size: 0.95rem;
  margin-top: 6px;
}
.kpi-up   { color: #d93025; } /* 빨강 */
.kpi-down { color: #1a73e8; } /* 파랑 */
.kpi-flat { color: #9aa0a6; } /* 보조 */
.small    { font-size: 0.85rem; color:#8b93a7;}
</style>
"""
st.markdown(CARD_CSS, unsafe_allow_html=True)

def render_card(title: str, last: float, prev: float, value_fmt="auto"):
    # 값/증감 계산
    delta = None
    pct = None
    if last is not None and prev not in (None, 0):
        delta = last - prev
        pct = (delta / prev) * 100

    # 색상 클래스 결정 (상승=빨강, 하락=파랑)
    if delta is None or math.isfinite(delta) is False:
        klass = "kpi-flat"
    elif delta > 0:
        klass = "kpi-up"
    elif delta < 0:
        klass = "kpi-down"
    else:
        klass = "kpi-flat"

    # 표시 형식
    if value_fmt == "krw":
        value_text = fmt_number(last, 2)
        delta_text = f"{fmt_number(delta, 2)}  ({fmt_percent(pct)})" if delta is not None else "-"
    elif value_fmt == "3dp":
        value_text = fmt_number(last, 3)
        delta_text = f"{fmt_number(delta, 3)}  ({fmt_percent(pct)})" if delta is not None else "-"
    else:
        value_text = fmt_number(last, 2)
        delta_text = f"{fmt_number(delta, 2)}  ({fmt_percent(pct)})" if delta is not None else "-"

    html = f"""
    <div class="kpi-card">
      <div class="kpi-title">{title}</div>
      <div class="kpi-value">{value_text}</div>
      <div class="kpi-delta {klass}">{delta_text}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# -----------------------------
# 대상 심볼 설정
# -----------------------------
# 지수
IDX = [
    ("KOSPI",   "^KS11",  "auto"),
    ("KOSDAQ",  "^KQ11",  "auto"),
    ("DOW",     "^DJI",   "auto"),
    ("NASDAQ",  "^IXIC",  "auto"),
]

# 환율/원자재
OTHERS = [
    ("USD/KRW", "KRW=X",  "krw"),   # 달러/원
    ("WTI",     "CL=F",   "auto"),
    ("Gold",    "GC=F",   "auto"),
    ("Copper",  "HG=F",   "3dp"),
]

# -----------------------------
# 헤더/시간
# -----------------------------
st.markdown("## 🧠 AI 뉴스리포트 종합 대시보드 (상단 요약)")

kst = ZoneInfo("Asia/Seoul")
now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S (KST)")
st.caption(f"업데이트 시간: {now_str}")

st.markdown("### 📈 오늘의 시장 요약")

# -----------------------------
# 1행: 지수 4개
# -----------------------------
cols = st.columns(len(IDX), gap="large")
for (i, (name, ticker, fmt)) in enumerate(IDX):
    with cols[i]:
        last, prev = fetch_quote(ticker)
        render_card(name, last, prev, value_fmt=fmt)

# -----------------------------
# 2행: 환율/원자재 4개
# -----------------------------
cols2 = st.columns(len(OTHERS), gap="large")
for (i, (name, ticker, fmt)) in enumerate(OTHERS):
    with cols2[i]:
        last, prev = fetch_quote(ticker)
        render_card(name, last, prev, value_fmt=fmt)

st.divider()
st.caption("※ 상승=빨강, 하락=파랑. 데이터 출처: Yahoo Finance (yfinance)")
