# app.py — pandas_datareader 없이 동작하는 버전
import os, json, re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple, Optional

import streamlit as st
import pandas as pd
import yfinance as yf
import feedparser

# ---------------- Common ----------------
KST = timezone(timedelta(hours=9))
st.set_page_config(page_title="AI 뉴스리포트 종합 대시보드", layout="wide")
st.markdown("# 🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")
st.caption("업데이트 시간: " + datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)"))

def kst_now_iso(): return datetime.now(KST).isoformat()

def load_json(path: str, default: Any):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def to_f(x):
    try:
        return None if x is None else float(x)
    except:
        return None

# ---------------- Market (yfinance only) ----------------
FALLBACK = {
    "KOSPI":  ["^KS11"],
    "KOSDAQ": ["^KQ11","^KOSDAQ","KQ11"],
    "USDKRW": ["KRW=X"],
    "WTI":    ["CL=F"],
    "Gold":   ["GC=F"],
    "Copper": ["HG=F"],
}

def _yf_last2(tick: str)->Tuple[Optional[float],Optional[float]]:
    try:
        df = yf.download(tick, period="10d", interval="1d", progress=False)
        c = df.get("Close")
        if c is None: return None, None
        vals = c.dropna().tail(2).tolist()
        if len(vals)==1: return float(vals[0]), None
        if len(vals)>=2: return float(vals[-1]), float(vals[-2])
    except:
        pass
    return None, None

def last2_any(candidates: List[str])->Tuple[Optional[float],Optional[float],Optional[str]]:
    for t in candidates:
        cur, prev = _yf_last2(t)
        if cur is not None:
            return cur, prev, t
    return None, None, None

def pct(cur, prev):
    try:
        if cur is None or prev in (None, 0): return None
        return round((cur-prev)/prev*100,2)
    except:
        return None

def load_market()->Dict[str,Any]:
    data = load_json("data/market_today.json", {})
    updated=False
    for name, cands in FALLBACK.items():
        cur = to_f(data.get(name,{}).get("value"))
        asof = data.get(name,{}).get("asof")
        stale = True
        try:
            if asof:
                stale = (datetime.now(KST)-datetime.fromisoformat(asof)).total_seconds()>6*3600
        except:
            pass
        if cur is None or stale:
            v, p, used = last2_any(cands)
            data[name] = {
                "value": None if v is None else round(v,2),
                "prev": None if p is None else round(p,2),
                "change_pct": pct(v,p),
                "ticker": used,
                "asof": kst_now_iso()
            }
            updated=True
    if updated:
        try:
            os.makedirs("data", exist_ok=True)
            with open("data/market_today.json","w",encoding="utf-8") as f:
                json.dump(data,f,ensure_ascii=False,indent=2)
        except:
            pass
    return data

# ---------------- News via Google RSS ----------------
NEWS_QUERIES = [
    "site:mk.co.kr 경제", "site:hankyung.com 경제", "site:biz.chosun.com 산업",
    "site:news1.kr 정책", "site:yna.co.kr 리포트", "site:policy.go.kr 정책브리핑"
]

def google_rss(query, hl="ko", gl="KR", ceid="KR:ko"):
    from urllib.parse import quote
    return f"https://news.google.com/rss/search?q={quote(query)}&hl={hl}&gl={gl}&ceid={ceid}"

def fetch_headlines_top10()->List[Dict[str,str]]:
    items=[]
    for q in NEWS_QUERIES:
        url=google_rss(q)
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                title = e.get("title","").strip()
                link  = e.get("link","").strip()
                if title and link:
                    items.append({"title":title,"link":link})
        except:
            pass
    # de-dup
    seen=set(); uniq=[]
    for it in items:
        if it["title"] in seen: continue
        seen.add(it["title"]); uniq.append(it)
    return uniq[:10]

# ---------------- Theme scoring ----------------
THEME_KEYWORDS = {
    "AI": ["AI","인공지능","생성형","챗GPT","LLM"],
    "반도체": ["반도체","HBM","파운드리","메모리","GPU","칩"],
    "로봇": ["로봇","협동로봇","자율주행로봇"],
    "이차전지": ["이차전지","배터리","양극재","음극재","전고체"],
    "바이오": ["바이오","제약","의약품","임상"],
    "조선": ["조선","선박","해운","LNG선"],
    "원전": ["원전","SMR","원자력"],
    "에너지": ["전력","정유","가스","재생에너지","풍력","태양광"],
}
THEME_STOCKS = {
    "AI": ["삼성전자","네이버","카카오","더존비즈온","티맥스소프트"],
    "반도체": ["삼성전자","SK하이닉스","DB하이텍","한미반도체","테스"],
    "로봇": ["레인보우로보틱스","유진로봇","티로보틱스","로보스타","현대로보틱스"],
    "이차전지": ["LG에너지솔루션","포스코퓨처엠","에코프로","에코프로비엠","엘앤에프"],
    "바이오": ["삼성바이오로직스","셀트리온","HLB","에스티팜","메디톡스"],
    "조선": ["HD한국조선해양","HD현대미포","삼성중공업","한화오션","HSD엔진"],
    "원전": ["두산에너빌리티","우진","한전KPS","한전기술","일진파워"],
    "에너지": ["한국전력","두산에너빌리티","GS","SK이노베이션","한국가스공사"],
}

def tokenize_ko(text:str)->List[str]:
    text = re.sub(r"[^0-9A-Za-z가-힣 ]"," ", text)
    return [t for t in text.split() if t]

def score_themes(news: List[Dict[str,str]])->pd.DataFrame:
    counts = {k:0 for k in THEME_KEYWORDS}
    sample = {k:"" for k in THEME_KEYWORDS}
    for n in news:
        title = n.get("title","")
        tokens = tokenize_ko(title)
        tset = " ".join(tokens)
        for theme, keys in THEME_KEYWORDS.items():
            if any(k in tset for k in keys):
                counts[theme]+=1
                if not sample[theme]: sample[theme]=n.get("link","#")
    rows=[]
    for th, ct in counts.items():
        if ct>0:
            rows.append({
                "theme": th,
                "count": ct,
                "score": ct,
                "rep_stocks": " · ".join(THEME_STOCKS.get(th, [])),
                "sample_link": sample[th]
            })
    return pd.DataFrame(rows).sort_values(["score","count"], ascending=False)

def monthly_keywords(news: List[Dict[str,str]])->pd.DataFrame:
    bag={}
    for n in news:
        for w in tokenize_ko(n.get("title","")):
            if len(w)<2: continue
            bag[w]=bag.get(w,0)+1
    rows = sorted(bag.items(), key=lambda x:x[1], reverse=True)[:30]
    return pd.DataFrame([{"keyword":k,"count":v} for k,v in rows])

# ---------------- Prepare data ----------------
market = load_market()

headlines = load_json("data/headlines_top10.json", [])
if not headlines:
    headlines = fetch_headlines_top10()
    try:
        os.makedirs("data", exist_ok=True)
        with open("data/headlines_top10.json","w",encoding="utf-8") as f:
            json.dump(headlines,f,ensure_ascii=False,indent=2)
    except:
        pass

themes_df = score_themes(headlines) if headlines else pd.DataFrame(columns=["theme","count","score","rep_stocks","sample_link"])
keywords_df = monthly_keywords(headlines) if headlines else pd.DataFrame(columns=["keyword","count"])

# ---------------- UI ----------------
def metric_block(col, title, entry: Dict[str,Any]):
    v = to_f(entry.get("value"))
    d = to_f(entry.get("change_pct"))
    if v is None: col.metric(title, value="-", delta="None")
    else: col.metric(title, value=f"{v:,.2f}", delta=("None" if d is None else f"{d:+.2f}%"))

st.subheader("📊 오늘의 시장 요약")
c1,c2,c3 = st.columns(3); c4,c5,c6 = st.columns(3)
metric_block(c1, "KOSPI"        , market.get("KOSPI",{}))
metric_block(c2, "KOSDAQ"       , market.get("KOSDAQ",{}))
metric_block(c3, "환율(USD/KRW)" , market.get("USDKRW",{}))
metric_block(c4, "WTI"          , market.get("WTI",{}))
metric_block(c5, "Gold"         , market.get("Gold",{}))
metric_block(c6, "Copper"       , market.get("Copper",{}))

st.divider()
st.subheader("📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")
if headlines is None or len(headlines)==0:
    st.info("헤드라인 없음")
else:
    for i,n in enumerate(headlines[:10], start=1):
        title = n.get("title","").replace("[","［").replace("]","］")
        link  = n.get("link","#") or "#"
        st.markdown(f"{i}. [{title}]({link})")

st.divider()
st.subheader("🔥 뉴스 기반 TOP 테마")
if themes_df is None or themes_df.empty:
    st.info("테마 데이터 없음")
else:
    st.bar_chart(themes_df.set_index("theme")["count"])
    with st.expander("전체 테마 집계 (대표 종목/샘플링크 포함)"):
        st.dataframe(themes_df.reset_index(drop=True), use_container_width=True)

st.divider()
st.subheader("🌐 월간 키워드맵 (최근 30일)")
if keywords_df is None or keywords_df.empty:
    st.info("키워드 없음")
else:
    st.bar_chart(keywords_df.set_index("keyword")["count"])

st.success("대시보드 로딩 완료 (데이터리더 의존 제거 버전)")
