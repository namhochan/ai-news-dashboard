# -*- coding: utf-8 -*-
"""
AI 뉴스리포트 – 완전 통합 풀버전 (2025-10-23)
지수·뉴스·테마·예측까지 자동 업데이트
"""

import math, re, numpy as np, pandas as pd
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus
from collections import Counter

import streamlit as st
import yfinance as yf
import feedparser
from bs4 import BeautifulSoup
from sklearn.linear_model import LogisticRegression

KST = ZoneInfo("Asia/Seoul")

# =========================================
# 🧠 기본 설정
# =========================================
st.set_page_config(page_title="AI 뉴스리포트 – 완전 통합버전", layout="wide")

def fmt_number(v, d=2):
    try: return f"{v:,.{d}f}" if v is not None and not math.isnan(v) else "-"
    except: return "-"

def fmt_percent(v):
    try: return f"{v:+.2f}%" if v is not None and not math.isnan(v) else "-"
    except: return "-"

# =========================================
# 📈 시세 수집
# =========================================
def fetch_quote(ticker: str):
    try:
        t = yf.Ticker(ticker)
        l, p = getattr(t.fast_info, "last_price", None), getattr(t.fast_info, "previous_close", None)
        if l and p: return float(l), float(p)
    except: pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False)
        c = df["Close"].dropna()
        if len(c)==0: return None,None
        return float(c.iloc[-1]), float(c.iloc[-2]) if len(c)>1 else None
    except: return None,None

# =========================================
# 📰 뉴스 수집 (Google RSS)
# =========================================
def clean_html(raw): return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)
def _parse_entries(feed, days):
    now=datetime.now(KST); out=[]
    for e in feed.entries:
        t=None
        if getattr(e,"published_parsed",None):
            t=datetime(*e.published_parsed[:6],tzinfo=KST)
        if t and (now-t).days>days: continue
        title,link=e.get("title",""),e.get("link","")
        if link.startswith("./"): link="https://news.google.com/"+link[2:]
        out.append({"title":title,"link":link,"time":t.strftime("%Y-%m-%d %H:%M") if t else "-", "desc":clean_html(e.get("summary",""))})
    return out

def fetch_google_news_by_keyword(kw,days=3):
    q=quote_plus(kw)
    url=f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed=feedparser.parse(url,request_headers={"User-Agent":"Mozilla/5.0"})
    return _parse_entries(feed,days)

CATEGORIES={
    "경제뉴스":["경제","금리","환율","무역","성장률"],
    "주식뉴스":["코스피","코스닥","증시","주가","외국인","기관매수"],
    "산업뉴스":["반도체","AI","로봇","자동차","배터리","수출입"],
    "정책뉴스":["정책","정부","예산","세금","규제","산업부"],
}

def fetch_category_news(cat,days=3,max_items=100):
    seen=set();out=[]
    for kw in CATEGORIES.get(cat,[]):
        for it in fetch_google_news_by_keyword(kw,days):
            k=(it["title"],it["link"])
            if k in seen:continue
            seen.add(k);out.append(it)
    out.sort(key=lambda x:x["time"],reverse=True)
    return out[:max_items]

# =========================================
# 💹 티커바
# =========================================
def build_ticker_items():
    rows=[("KOSPI","^KS11",2),("KOSDAQ","^KQ11",2),
          ("DOW","^DJI",2),("NASDAQ","^IXIC",2),
          ("USD/KRW","KRW=X",2),("WTI","CL=F",2),
          ("Gold","GC=F",2),("Copper","HG=F",3)]
    items=[]
    for name,ticker,dp in rows:
        l,p=fetch_quote(ticker)
        d=(l-p) if (l and p) else 0
        pct=(d/p*100) if (l and p) else 0
        items.append({"name":name,"last":fmt_number(l,dp),"pct":fmt_percent(pct),
                      "is_up":d>0,"is_down":d<0})
    return items

TICKER_CSS="""
<style>
.ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
.ticker-track{display:flex;gap:16px;align-items:center;width:max-content;
will-change:transform;animation:ticker-scroll var(--speed,30s) linear infinite;}
@keyframes ticker-scroll{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.badge{display:inline-flex;align-items:center;gap:8px;background:#0f1420;
border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap;}
.badge .name{color:#9fb3c8;font-weight:600;}
.badge .up{color:#e66;} .badge .down{color:#6aa2ff;}
</style>
"""
st.markdown(TICKER_CSS,unsafe_allow_html=True)
def render_ticker(items):
    chips=[]
    for it in items:
        arrow="▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        cls="up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(f"<span class='badge'><span class='name'>{it['name']}</span>{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>")
    line=" ".join(chips)
    st.markdown(f"<div class='ticker-wrap'><div class='ticker-track'>{line} {line}</div></div>",unsafe_allow_html=True)

st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
render_ticker(build_ticker_items())
st.caption("상승=빨강, 하락=파랑")

# =========================================
# 📰 최신 뉴스
# =========================================
st.divider()
st.markdown("## 📰 최신 뉴스 요약")
cat=st.selectbox("카테고리 선택",list(CATEGORIES))
page=st.number_input("페이지",1,10,1)
news_all=fetch_category_news(cat,3,100)
start=(page-1)*10
for n in news_all[start:start+10]:
    st.markdown(f"**[{n['title']}]({n['link']})**  \n<small>{n['time']}</small><br>{n['desc']}",unsafe_allow_html=True)
st.caption(f"최근 3일간 뉴스 {len(news_all)}건 중 {start+1}~{min(start+10,len(news_all))}")

# ==== 뉴스 기반 테마 요약 준비 (깨끗한 버전) ====
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

THEME_KEYWORDS = {
    "AI":        ["ai", "인공지능", "생성형", "챗봇", "오픈ai", "엔비디아", "gpu"],
    "반도체":     ["반도체", "hbm", "메모리", "파운드리", "칩", "램", "소부장"],
    "로봇":       ["로봇", "자율주행로봇", "amr", "협동로봇", "로보틱스"],
    "이차전지":    ["2차전지", "이차전지", "배터리", "전고체", "양극재", "음극재", "lfp"],
    "에너지":     ["에너지", "유가", "전력", "가스", "정유", "재생에너지", "풍력", "태양광"],
    "조선":       ["조선", "선박", "수주", "lng선", "해운"],
    "원전":       ["원전", "원자력", "smr", "원전수출", "원전정비"],
    "바이오":     ["바이오", "제약", "신약", "임상", "항암", "바이오시밀러"],
}

THEME_STOCKS = {
    "AI":       [("삼성전자","005930.KS"), ("네이버","035420.KS"), ("알체라","347860.KQ"), ("솔트룩스","304100.KQ")],
    "반도체":   [("SK하이닉스","000660.KS"), ("DB하이텍","000990.KS"), ("리노공업","058470.KQ"), ("한미반도체","042700.KQ")],
    "로봇":     [("레인보우로보틱스","277810.KQ"), ("유진로봇","056080.KQ"), ("티로보틱스","117730.KQ"), ("로보스타","090360.KQ")],
    "이차전지": [("에코프로","086520.KQ"), ("에코프로비엠","247540.KQ"), ("엘앤에프","066970.KQ"), ("포스코퓨처엠","003670.KS")],
    "에너지":   [("한국전력","015760.KS"), ("두산에너빌리티","034020.KS"), ("한화솔루션","009830.KS"), ("OCI홀딩스","010060.KS")],
    "조선":     [("HD한국조선해양","009540.KS"), ("HD현대미포","010620.KS"), ("한화오션","042660.KS"), ("삼성중공업","010140.KS")],
    "원전":     [("두산에너빌리티","034020.KS"), ("우진","105840.KQ"), ("한전KPS","051600.KS"), ("보성파워텍","006910.KQ")],
    "바이오":   [("셀트리온","068270.KS"), ("에스티팜","237690.KQ"), ("알테오젠","196170.KQ"), ("메디톡스","086900.KQ")],
}

def _normalize(s: str) -> str:
    return (s or "").lower()

def _detect_themes(news_list):
    counts = {t: 0 for t in THEME_KEYWORDS}
    sample_link = {t: "" for t in THEME_KEYWORDS}
    for n in news_list:
        text = _normalize(f"{n.get('title','')} {n.get('desc','')}")
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                counts[theme] += 1
                if not sample_link[theme]:
                    sample_link[theme] = n.get("link","")
    rows = []
    for t, c in counts.items():
        if c > 0:
            rows.append({
                "theme": t,
                "count": c,
                "sample_link": sample_link[t],
                "rep_stocks": " · ".join([nm for nm, _ in THEME_STOCKS.get(t, [])]) or "-",
            })
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows

# 🔧 여기서 ‘NULL 4개’가 뜨던 원인 제거: 리스트 컴프리헨션 출력 X, 명시적 for 루프 사용
all_news = []
for cat_name in CATEGORIES.keys():
    all_news.extend(fetch_category_news(cat_name, days=3, max_items=100))

theme_rows = _detect_themes(all_news)

# (이 아래로는 기존 표시 로직 그대로 사용)

# =========================================
# 🧠 뉴스 요약엔진 (더보기)
# =========================================
st.divider(); st.markdown("## 🧠 뉴스 요약엔진")
titles=[n["title"] for n in all_news]
words=[]; [words.extend(re.sub(r"[^가-힣A-Za-z0-9 ]"," ",t).split()) for t in titles]
kw=[w for w,_ in Counter([w for w in words if len(w)>=2]).most_common(10)]
st.markdown("**키워드 TOP10:** "+", ".join(kw))
summary=[s for s in re.split(r'[.!?]\s+', " ".join(titles)) if len(s.strip())>20][:5]
if summary:
    st.markdown(f"**요약:** {summary[0][:120]}...")
    with st.expander("전체 요약문 보기 👇"):
        for s in summary: st.markdown(f"- {s.strip()}")

# =========================================
# 📊 AI 상승확률 리포트 + 유망종목 Top5 + 예측
# =========================================
st.divider(); st.markdown("## 📊 AI 상승확률 리포트")

def avg_delta(stocks):
    arr=[]
    for _,t in stocks:
        l,p=fetch_quote(t)
        if l and p: arr.append((l-p)/p*100)
    return np.mean(arr) if arr else 0

rep=[]
for tr in theme_rows[:5]:
    theme=tr["theme"]; avg=avg_delta(THEME_STOCKS.get(theme,[]))
    level=1 if avg>2 else (2 if avg>0 else 3 if avg>-2 else 4)
    rep.append({"테마":theme,"뉴스빈도":tr["count"],"평균등락(%)":round(avg,2),"리스크레벨":level})
df=pd.DataFrame(rep); st.dataframe(df,use_container_width=True,hide_index=True)

# 🚀 유망종목 Top5
st.divider(); st.markdown("## 🚀 AI 유망 종목 Top5")
cand=[]
for tr in theme_rows[:8]:
    for n,t in THEME_STOCKS.get(tr["theme"],[]):
        l,p=fetch_quote(t)
        if l and p:
            d=(l-p)/p*100; score=tr["count"]*0.3+d*0.7
            cand.append({"테마":tr["theme"],"종목명":n,"등락률":round(d,2),"AI점수":round(score,2),"티커":t})
top5=pd.DataFrame(cand).sort_values("AI점수",ascending=False).head(5)
st.dataframe(top5,use_container_width=True,hide_index=True)

# 🔮 내일 오를 확률 (로지스틱 회귀)
st.divider(); st.markdown("## 🔮 3일 예측모듈")

def rsi(s,period=14):
    d=s.diff(); up=np.where(d>0,d,0); down=np.where(d<0,-d,0)
    roll_up=pd.Series(up).rolling(period).mean()
    roll_down=pd.Series(down).rolling(period).mean()
    rs=roll_up/roll_down.replace(0,np.nan)
    return 100-(100/(1+rs))

def build_feat(df):
    p=df["Close"]; f=pd.DataFrame(index=p.index)
    f["ret1"]=p.pct_change(1); f["rsi"]=rsi(p)
    f["ma5gap"]=(p-p.rolling(5).mean())/p.rolling(5).mean()
    f["ma20gap"]=(p-p.rolling(20).mean())/p.rolling(20).mean()
    f["y"]=(p.shift(-1)>p).astype(int)
    return f.dropna()

rows=[]
for _,r in top5.iterrows():
    try:
        dfh=yf.download(r["티커"],period="1y",interval="1d",progress=False)
        f=build_feat(dfh)
        X=f.drop("y",axis=1).values; y=f["y"].values
        if len(X)<60: continue
        model=LogisticRegression(max_iter=200).fit(X[:-3],y[:-3])
        prob=model.predict_proba(X[-3:])[:,1]
        rows.append({"종목명":r["종목명"],"티커":r["티커"],
                     "내일상승확률":round(prob[0]*100,1),"3일평균":round(prob.mean()*100,1)})
    except: continue

if rows:
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
else:
    st.info("예측 데이터 부족")

