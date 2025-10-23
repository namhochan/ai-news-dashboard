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
    page_title="AI 뉴스리포트 – 실시간 지수 티커바",
    page_icon="🧠",
    layout="wide",
)


# -----------------------------
# 포맷 유틸
# -----------------------------
def fmt_number(val: float, decimals: int = 2) -> str:
    """숫자 포맷팅 (비정상값은 '-')"""
    try:
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return "-"
        return f"{val:,.{decimals}f}"
    except Exception:
        return "-"


def fmt_percent(pct: float) -> str:
    """퍼센트 포맷팅 (+/- 기호 포함)"""
    try:
        if pct is None or (isinstance(pct, float) and (math.isnan(pct) or math.isinf(pct))):
            return "-"
        return f"{pct:+.2f}%"
    except Exception:
        return "-"


# -----------------------------
# 시세 가져오기 (안정형)
# -----------------------------
@st.cache_data(show_spinner=False, ttl=600)  # 10분 캐시
def fetch_quote(ticker: str):
    """
    1) yfinance.Ticker.fast_info 우선
    2) 실패 시 최근 7일 종가에서 마지막 2개로 계산
    => (last, prev) 튜플 반환. 실패 시 (None, None)
    """
    # fast_info 시도
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last is not None and prev is not None:
            return float(last), float(prev)
    except Exception:
        pass

    # history 백업
    try:
        df = yf.download(
            ticker,
            period="7d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False,
        )
        if df is None or df.empty or "Close" not in df:
            return None, None
        closes = df["Close"].dropna()
        if len(closes) == 0:
            return None, None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else last
        return last, prev
    except Exception:
        return None, None


# -----------------------------
# 티커바: CSS (무한루프 + 호버시 일시정지)
# -----------------------------
TICKER_CSS = """
<style>
.ticker-wrap {
  width: 100%;
  overflow: hidden;
  background: #111418;
  border-radius: 10px;
  border: 1px solid #222;
  padding: 8px 0;
}

/* 동일 콘텐츠를 2개 이어붙여 무한 루프처럼 스크롤 */
.ticker-track {
  display: flex;
  width: max-content;
  will-change: transform;
  animation: ticker-scroll 45s linear infinite;
}
.ticker-track:hover { animation-play-state: paused; }  /* 호버 시 일시정지 */

.ticker-seg {
  display: inline-block;
  white-space: nowrap;
  padding: 0 1.2rem;
  line-height: 1.5;
  font-size: 1.05rem;
}

.ticker-seg b { color: #e8eaed; font-weight: 700; }

.sep {
  opacity: .35;
  padding: 0 .6rem;
}

/* 핵심: 동일 콘텐츠 2개를 넣고 -50%까지만 이동하면 끊김 없이 반복됨 */
@keyframes ticker-scroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}

@media (prefers-reduced-motion: reduce) {
  .ticker-track { animation: none; }
}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)


# -----------------------------
# 대상 심볼
# -----------------------------
INDEXES = [
    ("KOSPI",   "^KS11"),
    ("KOSDAQ",  "^KQ11"),
    ("DOW",     "^DJI"),
    ("NASDAQ",  "^IXIC"),
    ("USD/KRW", "KRW=X"),
    ("WTI",     "CL=F"),
    ("Gold",    "GC=F"),
    ("Copper",  "HG=F"),
]


# -----------------------------
# 헤더/업데이트 시간
# -----------------------------
st.markdown("# 🧠 AI 뉴스리포트 – 실시간 지수 티커바")

kst = ZoneInfo("Asia/Seoul")
now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S (KST)")
st.caption(f"업데이트: {now_str}")

st.markdown("## 📈 오늘의 시장 요약")

# -----------------------------
# 티커 콘텐츠 1회분 생성
# -----------------------------
segments = []
for name, code in INDEXES:
    last, prev = fetch_quote(code)
    if last is None or prev is None:
        seg = f"<span class='ticker-seg'><b>{name}</b>&nbsp;<span style='color:#9aa0a6'>-</span></span>"
        segments.append(seg)
        continue

    diff = last - prev
    pct = (diff / prev) * 100 if prev != 0 else 0.0
    arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "–")
    color = "#d93025" if diff > 0 else ("#1a73e8" if diff < 0 else "#9aa0a6")

    seg = (
        f"<span class='ticker-seg'>"
        f"<b>{name}</b>&nbsp;"
        f"<span style='color:{color}; font-weight:700'>{fmt_number(last)} {arrow} {fmt_percent(pct)}</span>"
        f"</span>"
    )
    segments.append(seg)

# 콘텐츠 1회분을 두 번 이어붙여 무한루프 느낌으로
one_loop_html = "<span class='sep'>|</span>".join(segments)
full_html = f"""
<div class='ticker-wrap'>
  <div class='ticker-track'>
    <div class='ticker-loop'>{one_loop_html}</div>
    <div class='ticker-loop'>{one_loop_html}</div>
  </div>
</div>
"""

st.markdown(full_html, unsafe_allow_html=True)

st.caption("※ 상승=빨강 · 하락=파랑 · 데이터: Yahoo Finance (10분 캐시)")

# 간단 디버그(원할 때만 펼쳐보기)
with st.expander("🧪 디버그(수집결과 확인)"):
    rows = []
    for name, code in INDEXES:
        last, prev = fetch_quote(code)
        diff = (last - prev) if (last is not None and prev is not None) else None
        pct = (diff / prev * 100) if (diff is not None and prev not in (None, 0)) else None
        rows.append(
            {
                "name": name,
                "ticker": code,
                "last": last,
                "prev": prev,
                "diff": diff,
                "pct": pct,
            }
        )
    st.dataframe(pd.DataFrame(rows))
