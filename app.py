# app.py — 안정판 v2 (지수 백업심볼 + 확장 테마사전 + 불용어 필터)
import re, json
from datetime import datetime, timezone, timedelta
from typing import Dict, List

import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser
from urllib.parse import quote

# -------------------- 기본 설정 --------------------
KST = timezone(timedelta(hours=9))
st.set_page_config(page_title="AI 뉴스리포트 종합 대시보드", layout="wide")
st.markdown("# 🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")
st.caption("업데이트 시간: " + datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)"))

# -------------------- 유틸 --------------------
def normalize_item(x) -> Dict[str, str]:
    """뉴스 항목을 {'title','link'}로 강제"""
    try:
        if isinstance(x, dict) or "FeedParserDict" in x.__class__.__name__:
            t = str(x.get("title", "")).strip()
            l = str(x.get("link", "")).strip()
            return {"title": t, "link": l}
    except Exception:
        pass
    s = str(x).strip()
    return {"title": s, "link": ""}

def clean_title(t: str) -> str:
    """제목에서 불용 수식/괄호/날짜/매체 꼬리표 제거"""
    t = re.sub(r"\[[^\]]+\]", " ", t)        # [단독], [속보] 등
    t = re.sub(r"\([^\)]+\)", " ", t)        # (영상), (종합) 등
    t = re.sub(r"\d{1,2}월|\d{1,2}일|\d{4}년|\d{4}-\d{1,2}-\d{1,2}", " ", t)
    t = re.sub(r"[-–—]\s*[가-힣A-Za-z0-9_.]+(일보|신문|경제|뉴스|넷|TV|Biz|biz|net|com)$", " ", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t

# -------------------- 지수/환율/원자재 --------------------
# 심볼 후보를 여러 개 두고 순차 시도 (지역/세션에 따라 일부 빈값 방지)
SYMS = {
    "KOSPI":  ["^KS11", "^KS200"],              # 코스피 / 코스피200 백업
    "KOSDAQ": ["^KQ11", "^KOSDAQ", "KOSDAQ.KQ"],# 코스닥 후보
    "USDKRW": ["KRW=X"],
    "WTI":    ["CL=F"],
    "Gold":   ["GC=F"],
    "Copper": ["HG=F"],
}

def _last_two_close_v2(ticker: str):
    try:
        tk = yf.Ticker(ticker)
        df = tk.history(period="2mo", interval="1d", auto_adjust=True)
        closes = df["Close"].dropna().tail(2).tolist()
        if len(closes) == 2:
            return float(closes[-1]), float(closes[-2])
        elif len(closes) == 1:
            return float(closes[0]), None
    except Exception:
        pass
    return None, None

def get_market_block():
    out = {}
    for name, cands in SYMS.items():
        cur = prev = None
        for t in cands:
            cur, prev = _last_two_close_v2(t)
            if cur is not None:
                break
        if cur is None:
            out[name] = {"value": "-", "change": None}
        else:
            chg = None if prev is None or prev == 0 else round((cur - prev) / prev * 100, 2)
            out[name] = {"value": round(cur, 2), "change": chg}
    return out

# -------------------- 뉴스 (Google News RSS) --------------------
NEWS_QUERIES = [
    "site:mk.co.kr 경제",
    "site:hankyung.com 경제",
    "site:biz.chosun.com 산업",
    "site:yna.co.kr 정책",
    "site:policy.go.kr 정책브리핑",
]

def google_rss(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko"

def fetch_headlines_top10() -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for q in NEWS_QUERIES:
        url = google_rss(q)
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:8]:  # 출처당 8건
                n = normalize_item(e)
                n["title"] = clean_title(n["title"])
                items.append(n)
        except Exception:
            continue
    # 중복제거
    clean = []
    seen = set()
    for n in items:
        t, l = n.get("title", ""), n.get("link", "")
        if not t:
            continue
        key = t  # 제목 기준
        if key in seen:
            continue
        seen.add(key)
        clean.append({"title": t, "link": l})
    return clean[:10]

# -------------------- 테마 스코어링 --------------------
# 확장 사전: 동의어/하위키워드 다수 포함
THEMES = {
    "AI": ["AI","인공지능","생성형","챗GPT","LLM","NPU","온디바이스","코파일럿","에이아이"],
    "반도체": ["반도체","HBM","GPU","파운드리","메모리","디램","낸드","공정","미세화","첨단패키징","TSMC","엔비디아","클럭"],
    "이차전지": ["이차전지","2차전지","배터리","양극재","음극재","전고체","리튬","니켈","코발트","양극","음극"],
    "로봇": ["로봇","휴머노이드","자율주행","AGV","AMR","협동로봇","로보틱스","로보틱"],
    "바이오": ["바이오","제약","의약품","임상","신약","FDA","치료제","백신","항암"],
    "조선": ["조선","선박","해운","LNG선","컨테이너선","탱커","드릴십"],
    "원전": ["원전","원자력","SMR","가압경수로","원전수출","원전정비"],
    "에너지": ["에너지","정유","가스","천연가스","재생에너지","태양광","풍력","ESS"],
}

REP_STOCKS = {
    "AI": ["삼성전자","네이버","카카오","한글과컴퓨터","더존비즈온"],
    "반도체": ["삼성전자","SK하이닉스","DB하이텍","한미반도체","테스"],
    "이차전지": ["LG에너지솔루션","포스코퓨처엠","에코프로","에코프로비엠","엘앤에프"],
    "로봇": ["레인보우로보틱스","유진로봇","티로보틱스","로보스타"],
    "바이오": ["삼성바이오로직스","셀트리온","에스티팜","HLB"],
    "조선": ["HD한국조선해양","삼성중공업","한화오션","HD현대미포"],
    "원전": ["두산에너빌리티","한전KPS","한전기술","일진파워"],
    "에너지": ["한국전력","두산에너빌리티","GS","SK이노베이션","한국가스공사"],
}

# 한글/영문 공통 불용어
STOPWORDS = set("""
단독 속보 영상 포토 인터뷰 사설 칼럼 오피니언 기자 종합 특집
오늘 어제 내일 정부 발표 회의 관련 검토 추진 확정 전망 계획
한국경제 매일경제 한겨레 조선일보 중앙일보 연합뉴스 YTN MBC SBS KBS
""".split())

def score_themes(news: List[Dict[str, str]]) -> pd.DataFrame:
    counts = {k: 0 for k in THEMES}
    sample = {k: "" for k in THEMES}
    for raw in news:
        n = normalize_item(raw)
        title = clean_title(n.get("title", ""))
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
                "rep_stocks": " · ".join(REP_STOCKS.get(th, [])[:5]),
                "count": int(c),
                "sample_link": sample[th],
            })
    if not rows:
        return pd.DataFrame(columns=["theme","rep_stocks","count","sample_link"])
    return pd.DataFrame(rows).sort_values(["count","theme"], ascending=[False,True]).reset_index(drop=True)

def extract_keywords(news: List[Dict[str, str]]) -> pd.DataFrame:
    bag: Dict[str, int] = {}
    for raw in news:
        n = normalize_item(raw)
        title = clean_title(n.get("title", ""))
        # 토큰화
        for w in re.findall(r"[가-힣A-Za-z0-9]+", title):
            if len(w) < 2:
                continue
            if w in STOPWORDS:
                continue
            if re.fullmatch(r"\d+", w):
                continue
            bag[w] = bag.get(w, 0) + 1
    if not bag:
        return pd.DataFrame(columns=["keyword","count"])
    top = sorted(bag.items(), key=lambda x: x[1], reverse=True)[:30]
    return pd.DataFrame(top, columns=["keyword","count"])

# -------------------- 데이터 만들기 --------------------
market = get_market_block()
headlines = fetch_headlines_top10()
themes_df = score_themes(headlines)
keywords_df = extract_keywords(headlines)

# -------------------- UI --------------------
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
        t, l = n.get("title",""), n.get("link","")
        st.markdown(f"{i}. " + (f"[{t}]({l})" if l else t))

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

st.success("✅ 대시보드 로딩 완료 (지수 백업심볼/불용어/확장사전 적용)")
