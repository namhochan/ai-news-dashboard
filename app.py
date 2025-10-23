# -*- coding: utf-8 -*-
import math, re
import numpy as np
import pandas as pd
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
st.set_page_config(
    page_title="AI 뉴스리포트 – 자동 테마·시세 예측",
    layout="wide",
)

# 숫자 포맷
def fmt_number(v, d=2):
    try:
        if v is None or math.isnan(v): return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def fmt_percent(v):
    try:
        if v is None or math.isnan(v): return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

# =========================================
# 📈 시세 수집
# =========================================
def fetch_quote(ticker: str):
    try:
        t = yf.Ticker(ticker)
        last, prev = getattr(t.fast_info, "last_price", None), getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False)
        c = df["Close"].dropna()
        if len(c) == 0: return None, None
        return float(c.iloc[-1]), float(c.iloc[-2]) if len(c) > 1 else None
    except Exception:
        return None, None

# =========================================
# 📰 뉴스 수집 (Google RSS)
# =========================================
def clean_html(raw): return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days):
    now = datetime.now(KST)
    out = []
    for e in feed.entries:
        t = None
        if getattr(e, "published_parsed", None):
            t = datetime(*e.published_parsed[:6], tzinfo=KST)
        if t and (now - t).days > days: continue
        title, link = e.get("title", ""), e.get("link", "")
        if link.startswith("./"): link = "https://news.google.com/" + link[2:]
        desc = clean_html(e.get("summary", ""))
        out.append({"title": title, "link": link, "time": t.strftime("%Y-%m-%d %H:%M") if t else "-", "desc": desc})
    return out

def fetch_google_news_by_keyword(keyword, days=3, limit=40):
    q = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    return _parse_entries(feed, days)[:limit]

CATEGORIES = {
    "경제뉴스": ["경제","금리","물가","환율","성장률","무역"],
    "주식뉴스": ["코스피","코스닥","증시","주가","외국인 매수","기관 매도"],
    "산업뉴스": ["반도체","AI","배터리","자동차","로봇","수출입"],
    "정책뉴스": ["정책","정부","예산","규제","세금","산업부"],
}

def fetch_category_news(cat, days=3, max_items=100):
    seen=set(); out=[]
    for kw in CATEGORIES.get(cat, []):
        for it in fetch_google_news_by_keyword(kw, days):
            k=(it["title"],it["link"])
            if k in seen: continue
            seen.add(k); out.append(it)
    def key(x):
        try: return datetime.strptime(x["time"],"%Y-%m-%d %H:%M")
        except: return datetime.min
    return sorted(out,key=key,reverse=True)[:max_items]

# =========================================
# 💹 실시간 지수 티커바
# =========================================
def build_ticker_items():
    rows=[("KOSPI","^KS11",2),("KOSDAQ","^KQ11",2),
          ("DOW","^DJI",2),("NASDAQ","^IXIC",2),
          ("USD/KRW","KRW=X",2),("WTI","CL=F",2),
          ("Gold","GC=F",2),("Copper","HG=F",3)]
    items=[]
    for name,ticker,dp in rows:
        last,prev=fetch_quote(ticker)
        d,p=None,None
        if last and prev:
            d=last-prev; p=(d/prev)*100
        items.append({"name":name,"last":fmt_number(last,dp),
                      "pct":fmt_percent(p),"is_up":(d or 0)>0,"is_down":(d or 0)<0})
    return items

TICKER_CSS = """
<style>
.ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
.ticker-track{display:flex;gap:16px;align-items:center;width:max-content;
  will-change:transform;animation:ticker-scroll var(--speed,30s) linear infinite;}
@keyframes ticker-scroll{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.badge{display:inline-flex;align-items:center;gap:8px;background:#0f1420;
  border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap;}
.badge .name{color:#9fb3c8;font-weight:600;}
.badge .up{color:#e66;} .badge .down{color:#6aa2ff;} .sep{color:#44526b;padding:0 6px;}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

def render_ticker_line(items,speed_sec=30):
    chips=[]
    for it in items:
        arrow="▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        cls="up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(f"<span class='badge'><span class='name'>{it['name']}</span>{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>")
    line='<span class="sep">|</span>'.join(chips)
    st.markdown(f"<div class='ticker-wrap' style='--speed:{speed_sec}s'><div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>",unsafe_allow_html=True)

st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
col1,col2=st.columns([1,5])
with col1: st.markdown("### 📊 오늘의 시장 요약")
with col2:
    if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()
render_ticker_line(build_ticker_items())
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance")

# =========================================
# 📰 최신 뉴스 요약
# =========================================
st.divider()
st.markdown("## 📰 최신 뉴스 요약")
c1,c2=st.columns([2,1])
with c1: cat=st.selectbox("📂 카테고리 선택", list(CATEGORIES))
with c2: page=st.number_input("페이지",min_value=1,value=1,step=1)
news_all=fetch_category_news(cat,3,100)
page_size=10
news_page=news_all[(page-1)*page_size:page*page_size]
if not news_page: st.info("표시할 뉴스가 없습니다.")
else:
    for i,n in enumerate(news_page,1):
        st.markdown(f"**[{n['title']}]({n['link']})**  \n"
                    f"<span style='color:#9aa0a6;font-size:0.9rem;'>{n['time']}</span><br>"
                    f"<span style='color:#aeb8c5;'>{n['desc']}</span>",unsafe_allow_html=True)
        st.markdown("<hr style='border:0;border-top:1px solid #1f2937'/>",unsafe_allow_html=True)
st.caption(f"최근 3일 • {len(news_all)}건 중 {cat}")

# =========================================
# 🔥 뉴스 기반 테마 감지
# =========================================
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

THEME_KEYWORDS = {
    "AI":["ai","인공지능","챗봇","엔비디아","오픈ai","생성형"],
    "반도체":["반도체","hbm","칩","램","파운드리"],
    "로봇":["로봇","자율주행","협동로봇","amr"],
    "이차전지":["배터리","전고체","양극재","음극재","lfg"],
    "에너지":["에너지","정유","전력","태양광","풍력","가스"],
    "조선":["조선","선박","lNG선","해운"],
    "LNG":["lng","가스공사","터미널"],
    "원전":["원전","smr","원자력","우라늄"],
    "바이오":["바이오","제약","신약","임상"],
}

THEME_STOCKS = {  # 확장 풀
    "AI":[("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"),
           ("솔트룩스","304100.KQ"),("브레인즈컴퍼니","099390.KQ"),("한글과컴퓨터","030520.KS")],
    "반도체":[("SK하이닉스","000660.KS"),("DB하이텍","000990.KS"),("리노공업","058470.KQ"),
           ("원익IPS","240810.KQ"),("티씨케이","064760.KQ"),("에프에스티","036810.KQ")],
    "로봇":[("레인보우로보틱스","277810.KQ"),("유진로봇","056080.KQ"),("티로보틱스","117730.KQ"),
           ("로보스타","090360.KQ"),("스맥","099440.KQ")],
    "이차전지":[("LG에너지솔루션","373220.KS"),("포스코퓨처엠","003670.KS"),
           ("에코프로","086520.KQ"),("코스모신소재","005070.KQ"),("엘앤에프","066970.KQ")],
    "에너지":[("한국전력","015760.KS"),("두산에너빌리티","034020.KS"),
           ("GS","078930.KS"),("한화솔루션","009830.KS"),("OCI홀딩스","010060.KS")],
    "조선":[("HD한국조선해양","009540.KS"),("HD현대미포","010620.KS"),
           ("삼성중공업","010140.KS"),("한화오션","042660.KS")],
    "LNG":[("한국가스공사","036460.KS"),("지에스이","053050.KQ"),("대성에너지","117580.KQ"),("SK가스","018670.KS")],
    "원전":[("두산에너빌리티","034020.KS"),("우진","105840.KQ"),("한전KPS","051600.KS"),("보성파워텍","006910.KQ")],
    "바이오":[("셀트리온","068270.KS"),("에스티팜","237690.KQ"),("알테오젠","196170.KQ"),("메디톡스","086900.KQ")],
}

def detect_themes(news):
    counts={t:0 for t in THEME_KEYWORDS}
    for n in news:
        text=(n["title"]+" "+n["desc"]).lower()
        for t,kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws): counts[t]+=1
    rows=[{"theme":t,"count":c} for t,c in counts.items() if c>0]
    return sorted(rows,key=lambda x:x["count"],reverse=True)

all_news=[]
for c in CATEGORIES: all_news+=fetch_category_news(c,3,100)
theme_rows=detect_themes(all_news)
if not theme_rows: st.info("테마 신호 없음.")
else:
    top5=theme_rows[:5]
    st.markdown("**TOP 테마:** " + " ".join([f"🟢 {r['theme']}({r['count']})" for r in top5]))
    rng=np.random.default_rng(int(date.today().strftime("%Y%m%d")))

    def safe_yf_price(t):
        try:
            l,p=fetch_quote(t)
            if not l or not p: return None,None,"gray"
            d=(l-p)/p*100; c="red" if d>0 else ("blue" if d<0 else "gray")
            return fmt_number(l,0), fmt_percent(d), c
        except: return None,None,"gray"

    for tr in top5:
        theme=tr["theme"]; pool=THEME_STOCKS.get(theme,[])
        if not pool: continue
        idx=rng.choice(len(pool),size=min(4,len(pool)),replace=False)
        stocks=[pool[i] for i in idx]
        st.write(f"**{theme}**")
        cols=st.columns(len(stocks))
        for col,(name,ticker) in zip(cols,stocks):
            with col:
                px,chg,color=safe_yf_price(ticker)
                arrow="▲" if color=="red" else ("▼" if color=="blue" else "■")
                st.markdown(f"<b>{name}</b><br><span style='color:{color}'>{px} {arrow} {chg}</span><br><small>{ticker}</small>",unsafe_allow_html=True)
        st.divider()

# =========================================
# 🧠 AI 뉴스 요약엔진 (더보기형)
# =========================================
st.divider()
st.markdown("## 🧠 AI 뉴스 요약엔진")
titles=[n["title"] for c in CATEGORIES for n in fetch_category_news(c,3,60)]
words=[]
for t in titles:
    t=re.sub(r"[^가-힣A-Za-z0-9\s]"," ",t)
    words+=[w for w in t.split() if len(w)>=2]
top_kw=[w for w,_ in Counter(words).most_common(10)]
st.markdown("### 📌 핵심 키워드 TOP10")
st.write(", ".join(top_kw))
# 간단 요약문
full_text=" ".join(titles)
sentences=re.split(r'[.!?]\s+',full_text)
summary=[s for s in sentences if len(s.strip())>20][:5]
st.markdown("### 📰 핵심 요약문")
if summary:
    st.markdown(f"**요약:** {summary[0][:150]}...")
    with st.expander("전체 요약문 보기 👇"):
        for s in summary: st.markdown(f"- {s.strip()}")

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
