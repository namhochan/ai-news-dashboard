# app.py — 안정판 (입력 정규화 추가)
import re, json
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple

import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser

# ---------- 공통 ----------
KST = timezone(timedelta(hours=9))
st.set_page_config(page_title="AI 뉴스리포트 종합 대시보드", layout="wide")
st.markdown("# 🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")
st.caption("업데이트 시간: " + datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)"))

def to_float(x):
    try:
        return float(x) if x is not None else None
    except:
        return None

# ---------- 지수/환율/원자재 ----------
SYMS = {
    "KOSPI":  ["^KS11"],
    "KOSDAQ": ["^KQ11", "^KOSDAQ"],
    "USDKRW": ["KRW=X"],
    "WTI":    ["CL=F"],
    "Gold":   ["GC=F"],
    "Copper": ["HG=F"],
}

def _last_two_close(ticker: str):
    try:
        df = yf.download(ticker, period="10d", interval="1d", progress=False)
        closes = df["Close"].dropna().tail(2).tolist()
        if len(closes) == 2:
            return closes[-1], closes[-2]
        elif len(closes) == 1:
            return closes[0], None
    except:
        pass
    return None, None

def get_market_block():
    out = {}
    for name, cands in SYMS.items():
        cur = prev = None
        for t in cands:
            cur, prev = _last_two_close(t)
            if cur is not None:
                break
        if cur is None:
            out[name] = {"value": "-", "change": None}
        else:
            chg = None if prev is None else round((cur - prev) / prev * 100, 2)
            out[name] = {"value": round(cur, 2), "change": chg}
    return out

# ---------- 뉴스 수집 (Google News RSS) ----------
def google_rss(query: str) -> str:
    from urllib.parse import quote
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"

NEWS_QUERIES = [
    "site:mk.co.kr 경제",
    "site:hankyung.com 경제",
    "site:biz.chosun.com 산업",
    "site:yna.co.kr 정책",
    "site:policy.go.kr 정책브리핑",
]

def normalize_item(x) -> Dict[str, str]:
    """뉴스 항목을 무조건 {'title': str, 'link': str} 형태로 맞춤"""
    if isinstance(x, dict) or "FeedParserDict" in x.__class__.__name__:
        t = str(x.get("title", "")).strip()
        l = str(x.get("link", "")).strip()
        return {"title": t, "link": l}
    # 문자열 등 기타 타입
    s = str(x).strip()
    return {"title": s, "link": ""}

def fetch_headlines_top10() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for q in NEWS_QUERIES:
        url = google_rss(q)
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:6]:  # 각 소스 최대 6건
                items.append(normalize_item(e))
        except Exception:
            continue
    # 클린업
    clean = []
    seen = set()
    for n in items:
        t, l = n.get("title", ""), n.get("link", "")
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        clean.append({"title": t, "link": l})
    return clean[:10]

# ---------- 테마 스코어링 ----------
THEMES = {
    "AI": ["AI", "인공지능", "생성형", "챗GPT", "LLM"],
    "반도체": ["반도체", "HBM", "GPU", "파운드리", "메모리"],
    "이차전지": ["이차전지", "배터리", "양극재", "음극재", "전고체"],
    "로봇": ["로봇", "자율주행", "휴머노이드", "협동로봇"],
    "바이오": ["바이오", "제약", "의약품", "임상"],
    "조선": ["조선", "선박", "해운", "LNG선"],
    "원전": ["원전", "SMR", "원자력"],
}

REP_STOCKS = {
    "AI": ["삼성전자", "네이버", "카카오", "더존비즈온"],
    "반도체": ["삼성전자", "SK하이닉스", "DB하이텍"],
    "이차전지": ["LG에너지솔루션", "포스코퓨처엠", "에코프로"],
    "로봇": ["레인보우로보틱스", "유진로봇"],
    "바이오": ["삼성바이오로직스", "셀트리온"],
    "조선": ["HD한국조선해양", "삼성중공업"],
    "원전": ["두산에너빌리티", "한전KPS"],
}

def score_themes(news: List[Dict[str, str]]) -> pd.DataFrame:
    counts = {k: 0 for k in THEMES}
    sample = {k: "" for k in THEMES}
    for raw in news:
        n = normalize_item(raw)        # 💡 여기서 형태 강제
        title = n.get("title", "")
        link = n.get("link", "")
        for th, keys in THEMES.items():
            if any(k in title for k in keys):
                counts[th] += 1
                if not sample[th]:
                    sample[th] = link
    rows = []
    for th, c in counts.items():
        if c > 0:
            rows.append({
                "theme": th,
                "count": c,
                "rep_stocks": " · ".join(REP_STOCKS.get(th, [])),
                "sample_link": sample[th]
            })
    return pd.DataFrame(rows).sort_values("count", ascending=False)

def extract_keywords(news: List[Dict[str, str]]) -> pd.DataFrame:
    bag: Dict[str, int] = {}
    for raw in news:
        n = normalize_item(raw)
        for w in re.findall(r"[가-힣A-Za-z0-9]+", n.get("title", "")):
            if len(w) < 2:
                continue
            bag[w] = bag.get(w, 0) + 1
    top = sorted(bag.items(), key=lambda x: x[1], reverse=True)[:30]
    return pd.DataFrame(top, columns=["keyword", "count"])

# ---------- 데이터 생성 ----------
market = get_market_block()
headlines = fetch_headlines_top10()
themes_df = score_themes(headlines) if headlines else pd.DataFrame(columns=["theme", "count", "rep_stocks", "sample_link"])
keywords_df = extract_keywords(headlines) if headlines else pd.DataFrame(columns=["keyword", "count"])

# ---------- UI ----------
def metric(col, title, obj):
    val, chg = obj["value"], obj["change"]
    if val == "-":
        col.metric(title, value="-", delta="None")
    else:
        col.metric(title, value=f"{val:,.2f}", delta=("None" if chg is None else f"{chg:+.2f}%"))

st.subheader("📊 오늘의 시장 요약")
c1, c2, c3 = st.columns(3)
c4, c5, c6 = st.columns(3)
metric(c1, "KOSPI", market["KOSPI"])
metric(c2, "KOSDAQ", market["KOSDAQ"])
metric(c3, "환율(USD/KRW)", market["USDKRW"])
metric(c4, "WTI", market["WTI"])
metric(c5, "Gold", market["Gold"])
metric(c6, "Copper", market["Copper"])

st.divider()
st.subheader("📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")
if not headlines:
    st.info("헤드라인 없음")
else:
    for i, n in enumerate(headlines, start=1):
        n = normalize_item(n)
        t = n.get("title", "")
        l = n.get("link", "")
        if l:
            st.markdown(f"{i}. [{t}]({l})")
        else:
            st.markdown(f"{i}. {t}")

st.divider()
st.subheader("🔥 뉴스 기반 TOP 테마")
if themes_df.empty:
    st.info("테마 데이터 없음")
else:
    st.bar_chart(themes_df.set_index("theme")["count"])
    st.dataframe(themes_df, use_container_width=True)

st.divider()
st.subheader("🌐 월간 키워드맵 (최근 30일)")
if keywords_df.empty:
    st.info("키워드 없음")
else:
    st.bar_chart(keywords_df.set_index("keyword")["count"])

st.success("✅ 대시보드 로딩 완료 (강화된 입력 정규화 적용)")
