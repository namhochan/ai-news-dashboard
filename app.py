# -*- coding: utf-8 -*-
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import streamlit as st
import yfinance as yf
import feedparser
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------
# 페이지 설정
# ---------------------------------
st.set_page_config(
    page_title="AI 뉴스리포트 – 실시간 지수 티커바 + 최신 뉴스",
    layout="wide",
)

# ---------------------------------
# 공통 유틸
# ---------------------------------
def fmt_number(val: float, decimals: int = 2) -> str:
    try:
        if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
            return "-"
        return f"{val:,.{decimals}f}"
    except Exception:
        return "-"

def fmt_percent(pct: float) -> str:
    try:
        if pct is None or (isinstance(pct, float) and (math.isnan(pct) or math.isinf(pct))):
            return "-"
        return f"{pct:+.2f}%"
    except Exception:
        return "-"

# ---------------------------------
# 시세 수집 (안정형)
# ---------------------------------
def fetch_quote(ticker: str):
    """
    1) fast_info 시도
    2) 실패 시 최근 7일/1일봉 종가로 계산
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
        df = yf.download(ticker, period="7d", interval="1d", auto_adjust=False, progress=False)
        closes = df.get("Close")
        if df is None or closes is None or closes.dropna().empty:
            return None, None
        closes = closes.dropna()
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

def build_ticker_items():
    """
    티커바에 표시할 항목 구성
    """
    rows = [
        ("KOSPI",   "^KS11", 2),
        ("KOSDAQ",  "^KQ11", 2),
        ("DOW",     "^DJI",  2),
        ("NASDAQ",  "^IXIC", 2),
        ("USD/KRW", "KRW=X", 2),
        ("WTI",     "CL=F",  2),
        ("Gold",    "GC=F",  2),
        ("Copper",  "HG=F",  3),
    ]
    items = []
    for (name, ticker, dp) in rows:
        last, prev = fetch_quote(ticker)
        delta = None
        pct = None
        if last is not None and prev not in (None, 0):
            delta = last - prev
            pct = (delta / prev) * 100.0
        items.append({
            "name": name,
            "last": fmt_number(last, dp),
            "pct": fmt_percent(pct) if pct is not None else "--",
            "is_up": (delta or 0) > 0,
            "is_down": (delta or 0) < 0,
        })
    return items

# ---------------------------------
# 뉴스 수집 (Google News RSS) – 안정 버전
# ---------------------------------
def clean_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    return BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days: int):
    now = datetime.now(KST)
    items = []
    for e in feed.entries:
        pub_dt = None
        if getattr(e, "published_parsed", None):
            pub_dt = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            pub_dt = datetime(*e.updated_parsed[:6], tzinfo=KST)

        if pub_dt and (now - pub_dt) > timedelta(days=days):
            continue

        title = getattr(e, "title", "").strip()
        link = getattr(e, "link", "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
        desc = clean_html(getattr(e, "summary", ""))

        items.append({
            "title": title,
            "link": link,
            "time": pub_dt.strftime("%Y-%m-%d %H:%M") if pub_dt else "-",
            "desc": desc
        })
    return items

def fetch_google_news_by_keyword(keyword: str, days: int = 3, max_items: int = 40):
    """
    단일 키워드를 안전하게 RSS 조회 (User-Agent 지정)
    """
    q = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    items = _parse_entries(feed, days)
    return items[:max_items]

# 카테고리 → 여러 키워드
CATEGORIES = {
    "경제뉴스": ["경제", "물가", "환율", "무역", "금리", "성장률"],
    "주식뉴스": ["코스피", "코스닥", "증시", "주가", "외국인 매수", "기관 매매"],
    "산업뉴스": ["산업", "반도체", "배터리", "로봇", "제조", "수출입"],
    "정책뉴스": ["정책", "정부", "예산", "세금", "규제", "산업부", "금융위원회"],
}

def fetch_category_news(cat: str, days: int = 3, max_items: int = 100):
    """
    키워드별로 조회해서 합치고(중복 제거), 최신순 정렬
    """
    seen = set()
    merged = []
    for kw in CATEGORIES.get(cat, []):
        try:
            for it in fetch_google_news_by_keyword(kw, days=days, max_items=40):
                key = (it["title"], it["link"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(it)
        except Exception:
            continue

    def _key(x):
        try:
            return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.min

    merged.sort(key=_key, reverse=True)
    return merged[:max_items]

# ---------------------------------
# UI – 헤더 / 티커바
# ---------------------------------
st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
st.caption(f"업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}")

colL, colR = st.columns([1, 5])
with colL:
    st.markdown("### 📊 오늘의 시장 요약")
with colR:
    if st.button("🔄 새로고침", use_container_width=False):
        st.cache_data.clear()
        st.rerun()

# 티커 데이터
ticker_items = build_ticker_items()

TICKER_CSS = """
<style>
.ticker-wrap {
  position: relative; overflow: hidden; width: 100%;
  border: 1px solid #263042; border-radius: 10px; background: #0f1420;
}
.ticker {
  display: inline-block; white-space: nowrap;
  padding: 8px 0; animation: scroll-left var(--speed, 35s) linear infinite;
}
@keyframes scroll-left {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
.badge {
  display:inline-flex; align-items:center; gap:8px;
  background:#0f1420; border:1px solid #2b3a55; color:#c7d2fe;
  padding:6px 10px; margin:0 8px; border-radius:8px; font-weight:700;
}
.badge .name { color:#9fb3c8; font-weight:600; }
.badge .up   { color:#e66; }
.badge .down { color:#6aa2ff; }
.sep { color:#44526b; padding: 0 8px; }
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

def render_ticker_line(items, speed_sec=35):
    badges = []
    for it in items:
        arrow = "▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        pct_class = "up" if it["is_up"] else ("down" if it["is_down"] else "")
        badges.append(
            f'<span class="badge"><span class="name">{it["name"]}</span>'
            f'{it["last"]} <span class="{pct_class}">{arrow} {it["pct"]}</span></span>'
        )
    line = '<span class="sep">|</span>'.join(badges)
    # 두 번 이어붙여 끊김 없이
    html = f"""
    <div class="ticker-wrap" style="--speed:{speed_sec}s">
      <div class="ticker">{line} <span class="sep">|</span> {line}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

render_ticker_line(ticker_items, speed_sec=35)
st.caption("※ 상승=빨강, 하락=파랑 · 데이터 소스: Stooq → Yahoo → yfinance (10분 지연)")

st.divider()

# ---------------------------------
# UI – 최신 뉴스 (카테고리/페이지)
# ---------------------------------
st.markdown("## 📰 최신 뉴스 요약")

c1, c2 = st.columns([2, 1])
with c1:
    cat = st.selectbox("📂 카테고리 선택", list(CATEGORIES.keys()))
with c2:
    page = st.number_input("페이지", min_value=1, value=1, step=1)

# 데이터 로드
news_all = fetch_category_news(cat, days=3, max_items=100)
page_size = 10
total = len(news_all)
start = (page - 1) * page_size
end = start + page_size
news_page = news_all[start:end]

if not news_page:
    st.info("표시할 뉴스가 없습니다. (최근 3일 내 결과 없음)")
else:
    for i, n in enumerate(news_page, start=1 + start):
        title = n.get("title", "").strip() or "(제목 없음)"
        link = n.get("link", "")
        when = n.get("time", "-")
        desc = n.get("desc", "")

        st.markdown(
            f"**{i}. [{title}]({link})**  \n"
            f"<span style='color:#9aa0a6;font-size:0.9rem;'>{when}</span><br>"
            f"<span style='color:#aeb8c5;'>{desc}</span>",
            unsafe_allow_html=True
        )
        st.markdown("<hr style='border:0;border-top:1px solid #1f2937'/>", unsafe_allow_html=True)

st.caption(f"🗓 최근 3일 · 카테고리: {cat} · {total}개 중 {start+1}-{min(end,total)} 표시")

with st.expander("🧪 디버그(수집결과 및 요청 확인)"):
    st.write({"cat": cat, "total": total, "page": page, "start": start, "end": end})
