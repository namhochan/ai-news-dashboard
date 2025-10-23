# -*- coding: utf-8 -*-
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
import yfinance as yf

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(page_title="AI 뉴스리포트 – 실시간 지수 티커바", layout="wide")

KST = ZoneInfo("Asia/Seoul")

# -----------------------------
# 유틸
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
# 시세 수집 (안정형)
# -----------------------------
@st.cache_data(ttl=600)  # 10분 캐시
def fetch_quote(ticker: str):
    """
    1) fast_info 사용
    2) 실패 시 최근 7일 종가로 계산
    """
    # fast_info
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass

    # history 백업
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        closes = df.get("Close")
        if closes is None or closes.dropna().empty:
            return None, None
        closes = closes.dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# -----------------------------
# 대상 심볼
# -----------------------------
INDEXES = [
    ("KOSPI",   "^KS11",  2),
    ("KOSDAQ",  "^KQ11",  2),
    ("DOW",     "^DJI",   2),
    ("NASDAQ",  "^IXIC",  2),
    ("USD/KRW", "KRW=X",  2),
    ("WTI",     "CL=F",   2),
    ("Gold",    "GC=F",   2),
    ("Copper",  "HG=F",   3),
]

# -----------------------------
# 헤더 + 강제 새로고침(캐시 무시)
# -----------------------------
st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")

col_title, col_btn = st.columns([1, 0.16])
with col_title:
    st.markdown("### 📉 오늘의 시장 요약")
with col_btn:
    if st.button("🔄 강제 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

st.caption(f"업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}")

# -----------------------------
# 데이터 수집
# -----------------------------
rows = []
dbg = []

for name, ticker, dp in INDEXES:
    last, prev = fetch_quote(ticker)
    delta = pct = None
    if last is not None and prev not in (None, 0):
        delta = last - prev
        pct = (delta / prev) * 100

    rows.append({
        "name": name,
        "last": last,
        "prev": prev,
        "delta": delta,
        "pct": pct,
        "dp": dp
    })
    dbg.append({
        "name": name, "ticker": ticker,
        "last": last, "prev": prev, "delta": delta, "pct": pct
    })

df = pd.DataFrame(rows)

# -----------------------------
# 티커 문자열 만들기
# -----------------------------
items = []
for r in rows:
    name = r["name"]
    last = r["last"]
    pct  = r["pct"]
    dp   = r["dp"]

    last_txt = fmt_number(last, dp)
    pct_txt  = fmt_percent(pct)

    if pct is None or not math.isfinite(pct):
        color = "#9aa0a6"  # 회색
        arrow = ""
    elif pct > 0:
        color = "#d93025"  # 빨강(상승)
        arrow = "▲"
    elif pct < 0:
        color = "#1a73e8"  # 파랑(하락)
        arrow = "▼"
    else:
        color = "#9aa0a6"
        arrow = ""

    items.append(
        f"""<span class="tk-item">
             <span class="tk-name">{name}</span>
             <span class="tk-last">{last_txt}</span>
             <span class="tk-gap" style="color:{color};">{arrow} {pct_txt}</span>
           </span>"""
    )

# 콘텐츠를 두 번 이어 붙여 끊김 없이 순환
content = " <span class='tk-sep'>│</span> ".join(items)
content = (content + " <span class='tk-sep'>│</span> " + content)

# 콘텐츠 길이에 따라 속도 자동 조정(글자 수가 많으면 더 천천히)
base_speed = 18  # 기본 초
speed = base_speed + len(content) * 0.02  # 간단 가변 속도

# -----------------------------
# CSS Marquee (JS 없이 순수 CSS)
# -----------------------------
TICKER_CSS = f"""
<style>
.ticker-wrap {{
  position: relative;
  width: 100%;
  overflow: hidden;
  border: 1px solid #2b3340;
  border-radius: 12px;
  background: #0f1318;
  padding: 10px 0;
}}

.ticker-track {{
  display: inline-block;
  white-space: nowrap;
  will-change: transform;
  animation: ticker-move {speed:.1f}s linear infinite;
}}

@keyframes ticker-move {{
  0%   {{ transform: translate3d(0, 0, 0); }}
  100% {{ transform: translate3d(-50%, 0, 0); }}
}}

.tk-item {{
  display: inline-flex;
  align-items: baseline;
  gap: 8px;
  padding: 0 12px;
  font-size: 1.05rem;
}}

.tk-name {{ color:#cfd6e4; font-weight:700; }}
.tk-last {{ color:#cfd6e4; font-variant-numeric: tabular-nums; }}
.tk-gap  {{ font-weight:700; }}

.tk-sep  {{ color:#3b4352; padding: 0 6px; }}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

# -----------------------------
# 티커 렌더링
# -----------------------------
st.markdown(
    f"""
    <div class="ticker-wrap">
      <div class="ticker-track">{content}</div>
    </div>
    """,
    unsafe_allow_html=True
)

st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (yfinance, 10분 캐시)")

# -----------------------------
# 디버그: 수집 결과 확인
# -----------------------------
with st.expander("🧪 디버그(수집결과 확인)"):
    st.dataframe(pd.DataFrame(dbg))
