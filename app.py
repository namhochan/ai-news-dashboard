# -*- coding: utf-8 -*-
import math
import numpy as np
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
    # ================================
# 뉴스 기반 테마 감지 + 대표 종목 시세 (색상/아이콘 버전)
# ================================
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

THEME_KEYWORDS = {
    "AI":        ["ai", "인공지능", "생성형", "챗봇", "오픈AI", "엔비디아", "GPU"],
    "반도체":     ["반도체", "hbm", "메모리", "파운드리", "칩", "램", "소부장"],
    "로봇":       ["로봇", "자율주행로봇", "AMR", "협동로봇", "로보틱스"],
    "이차전지":    ["2차전지", "이차전지", "배터리", "전고체", "양극재", "음극재", "LFP"],
    "에너지":     ["에너지", "유가", "전력", "가스", "정유", "재생에너지", "풍력", "태양광"],
    "조선":       ["조선", "선박", "수주", "LNG선", "해운"],
    "LNG":       ["lng", "액화천연가스", "가스공사", "터미널"],
    "원전":       ["원전", "원자력", "SMR", "원전수출", "원전정비"],
    "바이오":     ["바이오", "제약", "신약", "임상", "항암", "바이오시밀러"],
}

THEME_STOCKS = {
    "AI":       [("삼성전자","005930.KS"), ("네이버","035420.KS"), ("카카오","035720.KS"), ("더존비즈온","012510.KS")],
    "반도체":   [("삼성전자","005930.KS"), ("SK하이닉스","000660.KS"), ("DB하이텍","000990.KS"), ("한미반도체","042700.KQ")],
    "로봇":     [("레인보우로보틱스","277810.KQ"), ("유진로봇","056080.KQ"), ("티로보틱스","117730.KQ"), ("로보스타","090360.KQ")],
    "이차전지": [("LG에너지솔루션","373220.KS"), ("포스코퓨처엠","003670.KS"), ("에코프로","086520.KQ"), ("에코프로비엠","247540.KQ")],
    "에너지":   [("한국전력","015760.KS"), ("두산에너빌리티","034020.KS"), ("GS","078930.KS"), ("SK이노베이션","096770.KS")],
    "조선":     [("HD한국조선해양","009540.KS"), ("HD현대미포","010620.KS"), ("삼성중공업","010140.KS"), ("한화오션","042660.KS")],
    "LNG":     [("한국가스공사","036460.KS"), ("지에스이","053050.KQ"), ("대성에너지","117580.KQ"), ("SK가스","018670.KS")],
    "원전":     [("두산에너빌리티","034020.KS"), ("우진","105840.KQ"), ("한전KPS","051600.KS"), ("한전기술","052690.KS")],
    "바이오":   [("삼성바이오로직스","207940.KS"), ("셀트리온","068270.KS"), ("에스티팜","237690.KQ"), ("메디톡스","086900.KQ")],
}

def normalize_text(s: str) -> str:
    return (s or "").lower()

def detect_themes(news_list):
    counts = {t: 0 for t in THEME_KEYWORDS}
    sample_link = {t: "" for t in THEME_KEYWORDS}

    for n in news_list:
        text = normalize_text(f"{n.get('title','')} {n.get('desc','')}")
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                counts[theme] += 1
                if not sample_link[theme]:
                    sample_link[theme] = n.get("link","")

    rows = []
    for theme, c in counts.items():
        if c > 0:
            rows.append({
                "theme": theme,
                "count": c,
                "sample_link": sample_link[theme],
                "rep_stocks": " · ".join([nm for nm, _ in THEME_STOCKS.get(theme, [])]) or "-",
            })
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows


all_news_3days = []
for cat_name in CATEGORIES.keys():
    all_news_3days.extend(fetch_category_news(cat_name, days=3, max_items=100))

theme_rows = detect_themes(all_news_3days)

if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다. (매칭 결과 없음)")
else:
    top5 = theme_rows[:5]
    badge_html = "<style>.tbadge{display:inline-block;margin:6px 6px 0 0;padding:6px 10px;border:1px solid #2b3a55;border-radius:10px;background:#0f1420} .tbadge b{color:#c7d2fe}</style>"
    st.markdown(badge_html, unsafe_allow_html=True)
    st.markdown("**TOP 테마**: " + " ".join([f"<span class='tbadge'><b>{r['theme']}</b> {r['count']}건</span>" for r in top5]), unsafe_allow_html=True)

    import pandas as pd
    st.dataframe(pd.DataFrame(theme_rows), use_container_width=True, hide_index=True)

    st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")

    def safe_yf_price(ticker):
        try:
            last, prev = fetch_quote(ticker)
            if last is None or prev in (None, 0):
                return None, None, "gray"
            delta = (last - prev) / prev * 100
            color = "red" if delta > 0 else ("blue" if delta < 0 else "gray")
            return fmt_number(last, 0), fmt_percent(delta), color
        except Exception:
            return None, None, "gray"

    for tr in top5:
        theme = tr["theme"]
        stocks = THEME_STOCKS.get(theme, [])
        if not stocks:
            continue
        st.write(f"**{theme}**")
        cols = st.columns(len(stocks))
        for col, (name, ticker) in zip(cols, stocks):
            with col:
                px, chg, color = safe_yf_price(ticker)
                if px:
                    arrow = "▲" if color == "red" else ("▼" if color == "blue" else "■")
                    st.markdown(f"<b>{name}</b><br><span style='color:{color}'>{px} {arrow} {chg}</span><br><small>{ticker}</small>", unsafe_allow_html=True)
                else:
                    st.markdown(f"**{name}**<br>-<br><small>{ticker}</small>", unsafe_allow_html=True)
        st.divider()
# =====================================
# 🧠 1단계: AI 뉴스 요약엔진 (더보기 버튼형)
# =====================================
import re
from collections import Counter

st.divider()
st.markdown("## 🧠 AI 뉴스 요약엔진")

def extract_keywords(texts, topn=10):
    """가장 많이 등장하는 단어 기반 키워드 추출"""
    words = []
    for t in texts:
        t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t)
        words.extend([w for w in t.split() if len(w) >= 2])
    counter = Counter(words)
    return [w for w, _ in counter.most_common(topn)]

def summarize_news(news_list, n_sent=5):
    """뉴스 내용 중 핵심 문장 상위 n개 추출"""
    texts = [n.get("title","") + " " + n.get("desc","") for n in news_list]
    if not texts:
        return []
    full_text = " ".join(texts)
    sentences = re.split(r'[.!?]\s+', full_text)
    sentences = [s for s in sentences if len(s.strip()) > 20]
    scores = {s: sum(word in full_text for word in s.split()) for s in sentences}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [s for s, _ in ranked[:n_sent]]

# 뉴스 데이터 기반 키워드 + 요약 생성
titles = [n["title"] for cat in CATEGORIES for n in fetch_category_news(cat, 3, 100)]
keywords = extract_keywords(titles, topn=10)
summary = summarize_news(all_news_3days, n_sent=5)

# 핵심 키워드 출력
st.markdown("### 📌 핵심 키워드 TOP10")
if keywords:
    st.write(", ".join(keywords))
else:
    st.info("키워드 데이터가 부족합니다.")

# 더보기 버튼형 요약문
st.markdown("### 📰 핵심 요약문")
if summary:
    st.markdown(f"**요약:** {summary[0][:150]}...")  # 첫 줄만 미리 보여줌
    with st.expander("전체 요약문 보기 👇"):
        for s in summary:
            st.markdown(f"- {s.strip()}")
else:
    st.info("요약 데이터를 가져오지 못했습니다.")

# =====================================
# 📊 2단계: 테마별 상승 확률 예측 (AI 리스크레벨 + 테마강도)
# =====================================
st.divider()
st.markdown("## 📊 AI 상승 확률 예측 리포트")

def calc_theme_strength(count, avg_delta):
    """테마강도: 뉴스빈도(0~1) + 평균등락(0~1)"""
    freq_score = min(count / 20, 1.0)
    price_score = min(max((avg_delta + 5) / 10, 0), 1.0)
    total = (freq_score * 0.6 + price_score * 0.4) * 5
    return round(total, 1)

def calc_risk_level(avg_delta):
    """AI 리스크 레벨 (1~5, 하락폭 클수록 높음)"""
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

report_rows = []
for tr in theme_rows[:5]:
    theme = tr["theme"]
    stocks = THEME_STOCKS.get(theme, [])
    deltas = []
    for _, ticker in stocks:
        try:
            last, prev = fetch_quote(ticker)
            if last and prev:
                deltas.append((last - prev) / prev * 100)
        except Exception:
            pass
    avg_delta = np.mean(deltas) if deltas else 0
    theme_strength = calc_theme_strength(tr["count"], avg_delta)
    risk_level = calc_risk_level(avg_delta)
    report_rows.append({
        "테마": theme,
        "뉴스빈도": tr["count"],
        "평균등락(%)": round(avg_delta, 2),
        "테마강도(1~5)": theme_strength,
        "리스크레벨(1~5)": risk_level,
    })

st.dataframe(report_rows, use_container_width=True, hide_index=True)
st.caption("※ 테마강도↑ = 뉴스 + 가격이 모두 활발한 상태 / 리스크레벨↑ = 변동성·하락 가능성 높음")
# =====================================
# 🚀 3단계: AI 유망 종목 자동 추천 (Top5)
# =====================================
st.divider()
st.markdown("## 🚀 오늘의 AI 유망 종목 Top5")

def pick_promising_stocks(theme_rows, top_n=5):
    """
    테마 강도 + 평균 등락률을 바탕으로 유망 종목 선별
    1) 테마강도 높은 순
    2) 그 테마 내 상승률 상위 종목
    """
    candidates = []
    for tr in theme_rows[:8]:  # 상위 테마 몇 개만
        theme = tr["theme"]
        stocks = THEME_STOCKS.get(theme, [])
        for name, ticker in stocks:
            try:
                last, prev = fetch_quote(ticker)
                if not last or not prev:
                    continue
                delta = (last - prev) / prev * 100
                score = tr["count"] * 0.3 + delta * 0.7
                candidates.append({
                    "테마": theme,
                    "종목명": name,
                    "등락률(%)": round(delta, 2),
                    "뉴스빈도": tr["count"],
                    "AI점수": round(score, 2),
                    "티커": ticker
                })
            except Exception:
                continue

    df = pd.DataFrame(candidates)
    if df.empty:
        return pd.DataFrame()
    df = df.sort_values(by="AI점수", ascending=False).head(top_n)
    return df

recommend_df = pick_promising_stocks(theme_rows, top_n=5)

if recommend_df.empty:
    st.info("추천할 종목이 없습니다. 데이터가 부족하거나 시장 변동성이 낮습니다.")
else:
    st.dataframe(recommend_df, use_container_width=True, hide_index=True)
    st.markdown("### 🧾 AI 종합 판단")
    for _, row in recommend_df.iterrows():
        emoji = "🔺" if row["등락률(%)"] > 0 else "🔻"
        st.markdown(
            f"**{emoji} {row['종목명']} ({row['티커']})** — "
            f"테마: *{row['테마']}*, 최근 등락률: **{row['등락률(%)']}%**, "
            f"뉴스빈도: {row['뉴스빈도']}건, AI점수: {row['AI점수']}"
        )

st.caption("※ AI점수 = 뉴스활성도 + 주가상승률 기반 유망도 산출")
# =====================================
# 🔮 4단계: '내일 오를 확률' 3일 예측 모듈
#  - 각 종목의 과거 일봉으로 간단한 로지스틱 회귀를 학습(슬라이딩, 누수방지)
#  - 특징: 모멘텀/변동성/RSI/이평괴리/MACD
#  - 출력: 내일(+1) 수익률>0 확률, 3일 평균 확률, 매수/관망 신호
# =====================================
st.divider()
st.markdown("## 🔮 AI 3일 예측: 내일 오를 확률")

import numpy as np
from sklearn.linear_model import LogisticRegression

if 'recommend_df' not in globals() or recommend_df.empty:
    st.info("먼저 상단의 '유망 종목 Top5'가 생성되어야 예측을 수행할 수 있어요.")
else:
    # --------- 유틸: 지표 ----------
    def rsi(series: pd.Series, period: int = 14):
        delta = series.diff()
        up = np.where(delta > 0, delta, 0.0)
        down = np.where(delta < 0, -delta, 0.0)
        roll_up = pd.Series(up, index=series.index).rolling(period).mean()
        roll_down = pd.Series(down, index=series.index).rolling(period).mean()
        rs = roll_up / (roll_down.replace(0, np.nan))
        r = 100 - (100 / (1 + rs))
        return r.fillna(50)

    def macd(series: pd.Series, fast=12, slow=26, signal=9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        hist = macd_line - signal_line
        return macd_line, signal_line, hist

    @st.cache_data(ttl=600)
    def load_hist(ticker: str, period="2y"):
        df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
        # 야후 쿼터/휴장 이슈 방지
        df = df[~df.index.duplicated(keep='last')].dropna()
        return df

    def build_features(df: pd.DataFrame):
        price = df["Close"]
        feat = pd.DataFrame(index=df.index)
        # 모멘텀
        feat["ret_1d"] = price.pct_change(1)
        feat["ret_5d"] = price.pct_change(5)
        feat["ret_10d"] = price.pct_change(10)
        # 변동성
        feat["vol_5d"] = df["Close"].pct_change().rolling(5).std()
        feat["vol_20d"] = df["Close"].pct_change().rolling(20).std()
        # RSI / MACD
        feat["rsi_14"] = rsi(price, 14)
        macd_line, signal_line, hist = macd(price)
        feat["macd"] = macd_line
        feat["macd_sig"] = signal_line
        feat["macd_hist"] = hist
        # 이평괴리
        ma5 = price.rolling(5).mean(); ma20 = price.rolling(20).mean()
        feat["ma5_gap"] = (price - ma5) / ma5
        feat["ma20_gap"] = (price - ma20) / ma20
        # 타깃(내일 상승?)
        tgt = (price.shift(-1) > price).astype(int)
        data = pd.concat([feat, tgt.rename("y")], axis=1).dropna()
        return data

    def fit_predict_prob(df_feat: pd.DataFrame):
        """
        단순 로지스틱 회귀. 최근 250거래일 학습, 마지막 3일 예측 확률 반환.
        시계열 누수 방지를 위해 과거 구간만으로 학습.
        """
        if len(df_feat) < 120:
            return None, None  # 데이터 부족
        data = df_feat.copy().tail(300)  # 계산 가벼움 유지
        X = data.drop(columns=["y"]).values
        y = data["y"].values
        # 학습/예측 분리: 마지막 3개를 '예측 구간'으로
        n = len(data)
        split = max(60, n - 3)  # 최소 60일은 학습 확보
        X_train, y_train = X[:split], y[:split]
        X_pred = X[split:]
        model = LogisticRegression(max_iter=200, n_jobs=None)
        model.fit(X_train, y_train)
        prob = model.predict_proba(X_pred)[:, 1]  # 상승확률
        # 내일(가장 첫 번째 예측)과 3일 평균
        p_tomorrow = float(prob[0]) if len(prob) > 0 else None
        p_3avg = float(prob.mean()) if len(prob) > 0 else None
        return p_tomorrow, p_3avg

    rows = []
    with st.spinner("예측 계산 중..."):
        for _, r in recommend_df.iterrows():
            name, ticker = r["종목명"], r["티커"]
            try:
                hist = load_hist(ticker)
                feats = build_features(hist)
                p1, p3 = fit_predict_prob(feats)
                if p1 is None:
                    rows.append({"종목명": name, "티커": ticker, "내일상승확률": "-", "3일평균확률": "-", "신호": "데이터부족"})
                    continue
                signal = "매수관심" if p1 >= 0.55 else ("관망" if p1 >= 0.45 else "주의")
                rows.append({
                    "종목명": name,
                    "티커": ticker,
                    "내일상승확률": round(p1 * 100, 1),
                    "3일평균확률": round(p3 * 100, 1),
                    "신호": signal
                })
            except Exception:
                rows.append({"종목명": name, "티커": ticker, "내일상승확률": "-", "3일평균확률": "-", "신호": "오류"})

    pred_df = pd.DataFrame(rows)

    if pred_df.empty:
        st.info("예측을 표시할 데이터가 없습니다.")
    else:
        # 색상 하이라이트: 확률/신호
        def _prob_color(v):
            try:
                v = float(v)
            except:
                return ""
            if v >= 60:  # 높음
                return "background-color: rgba(217,48,37,0.2); color:#ffd2cf; font-weight:700;"
            if v >= 50:  # 보통
                return "background-color: rgba(255,193,7,0.15);"
            return "background-color: rgba(26,115,232,0.18); color:#d7e6ff;"

        st.dataframe(
            pred_df.style.map(_prob_color, subset=["내일상승확률", "3일평균확률"]),
            use_container_width=True, hide_index=True
        )

        # 요약 문장
        st.markdown("### 🧠 AI 인사이트")
        for _, row in pred_df.iterrows():
            if row["내일상승확률"] == "-":
                st.markdown(f"- **{row['종목명']} ({row['티커']})** — 데이터 부족/오류로 예측 생략")
            else:
                arrow = "🔺" if row["내일상승확률"] >= 50 else "🔻"
                st.markdown(
                    f"- **{row['종목명']} ({row['티커']})** — 내일 상승 확률 **{row['내일상승확률']}%** "
                    f"(3일 평균 {row['3일평균확률']}%), 신호: **{row['신호']}** {arrow}"
                )

st.caption("※ 간단한 로지스틱 회귀 기반 참고지표입니다. 투자 판단의 책임은 본인에게 있습니다.")
