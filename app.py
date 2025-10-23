import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
import yfinance as yf
import feedparser
from bs4 import BeautifulSoup

# -----------------------------
# 공통 설정
# -----------------------------
st.set_page_config(page_title="AI 뉴스리포트 – 실시간 지수 티커바", layout="wide")
KST = ZoneInfo("Asia/Seoul")

def fmt_number(val: float, decimals: int = 2) -> str:
    if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
        return "-"
    return f"{val:,.{decimals}f}"

def fmt_percent(pct: float) -> str:
    if pct is None or (isinstance(pct, float) and (math.isnan(pct) or math.isinf(pct))):
        return "-"
    return f"{pct:+.2f}%"

# -----------------------------
# 시세 가져오기 (yfinance 안전 모드)
# -----------------------------
def fetch_quote(ticker: str):
    # 1) fast_info
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass
    # 2) 최근 7일 종가
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        if df.empty:
            return None, None
        closes = df["Close"].dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# -----------------------------
# 티커바 렌더링
# -----------------------------
def make_chip(name: str, last: float, prev: float):
    delta = None
    pct = None
    if last is not None and prev not in (None, 0):
        delta = last - prev
        pct = (delta / prev) * 100

    if delta is None:
        klass = "flat"
        delta_txt = "-"
    elif delta > 0:
        klass = "up"
        delta_txt = f"▲ {fmt_percent(pct)}"
    elif delta < 0:
        klass = "down"
        delta_txt = f"▼ {fmt_percent(pct)}"
    else:
        klass = "flat"
        delta_txt = "0.00%"

    return f"""
    <span class="chip {klass}">
      <b>{name}</b> {fmt_number(last,2)} <span class="delta">{delta_txt}</span>
    </span>
    """

TICKER_CSS = """
<style>
.tbar { display:flex; gap:10px; overflow-x:auto; white-space:nowrap;
        border:1px solid #2b3445; padding:10px 12px; border-radius:12px; }
.chip { border-radius:999px; padding:6px 12px; background:#0e1116; border:1px solid #2b3445; }
.chip .delta { margin-left:6px; font-weight:700; }
.up   { color:#e86d6d; }
.down { color:#4aa3ff; }
.flat { color:#9aa0a6; }
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

st.markdown("# 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
st.caption("업데이트: " + datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)"))

# 상단 버튼(강제 새로고침)
col1, col2 = st.columns([1,6])
with col1:
    if st.button("🔄 강제 새로고침"):
        st.rerun()

st.subheader("📈 오늘의 시장 요약")

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

chips = []
for name, tick in INDEXES:
    last, prev = fetch_quote(tick)
    chips.append(make_chip(name, last, prev))

st.markdown(f'<div class="tbar">{" | ".join(chips)}</div>', unsafe_allow_html=True)
st.caption("※ 상승=빨강, 하락=파랑 · 데이터 소스: Stooq ➜ Yahoo → yfinance (10분 지연)")

# =============================
# 📰 Google News RSS (3일/카테고리/10개씩 페이지)
# =============================
st.divider()
st.markdown("## 📰 최신 뉴스 요약")

def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)

def fetch_google_news(query: str, days: int = 3, max_items: int = 100):
    """
    Google News RSS
    - q 파라미터를 URL 인코딩(quote_plus)하여 InvalidURL 방지
    - when:3d 조건 포함
    - 한국어/한국 지역
    """
    # q 파라미터만 인코딩!
    q = quote_plus(f"({query}) when:{days}d")
    rss_url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"

    feed = feedparser.parse(rss_url)
    now = datetime.now(KST)
    items = []
    for e in feed.entries[:max_items]:
        try:
            title = e.title
            # 상대경로를 절대경로로 보정
            link = e.link
            if link.startswith("./"):
                link = "https://news.google.com/" + link[2:]
            # 발행 시각
            published = "-"
            if hasattr(e, "published_parsed") and e.published_parsed:
                pub_dt = datetime(*e.published_parsed[:6])
                # 3일 필터
                if (now - pub_dt) > timedelta(days=days):
                    continue
                published = pub_dt.strftime("%Y-%m-%d %H:%M")
            desc = clean_html(e.get("summary", ""))
            items.append({"title": title, "link": link, "time": published, "desc": desc})
        except Exception:
            continue
    return items

CATEGORIES = {
    "경제뉴스": "경제 OR 물가 OR 환율 OR 무역 OR 금리 OR 성장률",
    "주식뉴스": "코스피 OR 코스닥 OR 증시 OR 주가 OR 매수 OR 기관 OR 외국인",
    "산업뉴스": "산업 OR 반도체 OR 배터리 OR 로봇 OR 제조 OR 수출입",
    "정책뉴스": "정책 OR 정부 OR 예산 OR 세금 OR 규제 OR 지원 OR 산업부 OR 금융위",
}

# 데이터 수집 (카테고리별 100개까지)
news_data = {}
for cat, query in CATEGORIES.items():
    try:
        news_data[cat] = fetch_google_news(query, days=3, max_items=100)
    except Exception as e:
        news_data[cat] = []
        st.warning(f"{cat} 수집 중 오류: {e}")

# UI: 카테고리 + 페이지
left, right = st.columns([2,1])
with left:
    cat_selected = st.selectbox("📂 카테고리 선택", list(CATEGORIES.keys()))
with right:
    total = len(news_data.get(cat_selected, []))
    per_page = 10
    max_page = max(1, (total - 1) // per_page + 1)
    page = st.number_input("페이지", min_value=1, max_value=max_page, value=1, step=1)

start = (page - 1) * per_page
end = start + per_page
subset = news_data.get(cat_selected, [])[start:end]

if not subset:
    st.info("표시할 뉴스가 없습니다. (최근 3일 이내 결과 없음)")
else:
    for n in subset:
        st.markdown(f"#### [{n['title']}]({n['link']})")
        st.caption(f"🕒 {n['time']}")
        if n["desc"]:
            st.write(n["desc"])
        st.markdown("---")

st.caption(
    f"📆 최근 3일 | 카테고리: {cat_selected} | "
    f"{len(news_data.get(cat_selected, []))}개 중 {start+1}–{min(end, len(news_data.get(cat_selected, [])))} 표시"
    )
