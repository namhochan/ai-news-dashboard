# -*- coding: utf-8 -*-
import math, re, difflib
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus
from collections import Counter

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
import feedparser
from bs4 import BeautifulSoup
from sklearn.linear_model import LogisticRegression
import FinanceDataReader as fdr

KST = ZoneInfo("Asia/Seoul")
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")

# -------------------------
# 공통 유틸
# -------------------------
def now_kst_str(): return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)")
def fmt_number(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return "-"
        return f"{v:,.{d}f}"
    except Exception: return "-"
def fmt_percent(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return "-"
        return f"{v:+.2f}%"
    except Exception: return "-"

def valid_prices(last, prev):
    return last is not None and prev not in (None, 0) and all(map(np.isfinite, [last, prev]))

# -------------------------
# 시세
# -------------------------
@st.cache_data(ttl=900)
def fetch_quote(ticker: str):
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if valid_prices(last, prev): return float(last), float(prev)
    except Exception:
        pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        c = df.get("Close")
        if c is None or c.dropna().empty: return None, None
        c = c.dropna()
        last = float(c.iloc[-1]); prev = float(c.iloc[-2]) if len(c) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# -------------------------
# 뉴스 (Google RSS)
# -------------------------
def clean_html(raw): return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

@st.cache_data(ttl=900)
def fetch_google_news_by_keyword(keyword, days=3, limit=50):
    q = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    now = datetime.now(KST)
    out = []
    for e in getattr(feed, "entries", []):
        t = None
        if getattr(e, "published_parsed", None):
            t = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            t = datetime(*e.updated_parsed[:6], tzinfo=KST)
        if t and (now - t) > timedelta(days=days): 
            continue
        title, link = e.get("title", ""), e.get("link", "")
        if link.startswith("./"): link = "https://news.google.com/" + link[2:]
        out.append({"title": title.strip(), "link": link.strip(),
                    "time": t.strftime("%Y-%m-%d %H:%M") if t else "-",
                    "desc": clean_html(e.get("summary",""))})
    # 최신순
    def key(x):
        try: return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except: return datetime.min
    out.sort(key=key, reverse=True)
    return out[:limit]

CATEGORIES = {
    "경제뉴스": ["경제","금리","물가","환율","성장률","무역"],
    "주식뉴스": ["코스피","코스닥","증시","주가","외국인 매수","기관 매도"],
    "산업뉴스": ["반도체","AI","배터리","자동차","로봇","전력","전기요금","에너지","데이터센터"],
    "정책뉴스": ["정책","정부","예산","규제","세금","산업부","금융위원회"],
}

@st.cache_data(ttl=900)
def fetch_category_news(cat, days=3, max_items=120):
    seen, out = set(), []
    for kw in CATEGORIES.get(cat, []):
        for it in fetch_google_news_by_keyword(kw, days, 50):
            k = (it["title"], it["link"])
            if k in seen: continue
            seen.add(k); out.append(it)
    return out[:max_items]

# -------------------------
# KRX 자동 매핑 유틸
# -------------------------
@st.cache_data(ttl=3600)
def load_krx_listings():
    df = fdr.StockListing("KRX")
    df = df.rename(columns={"Symbol":"Code","Name":"Name"})
    for col in ["Name","Sector","Industry"]:
        if col not in df.columns: df[col] = ""
    df["name_l"]    = df["Name"].astype(str).str.lower()
    df["sector_l"]  = df["Sector"].astype(str).str.lower()
    df["industry_l"]= df["Industry"].astype(str).str.lower()
    return df[["Code","Name","Market","Sector","Industry","name_l","sector_l","industry_l"]]

def _kr_ticker(code: str) -> str|None:
    if not code or not re.fullmatch(r"\d{6}", str(code)): return None
    return f"{code}.KS" if str(code)[0] in "01569" else f"{code}.KQ"

def extract_company_mentions(news_list, listings, min_len=2, sim_cutoff=0.9):
    idx_by_name = {n: i for i, n in enumerate(listings["name_l"].tolist())}
    names = list(idx_by_name.keys())
    counts = {}
    for n in news_list:
        text = (n.get("title","") + " " + n.get("desc","")).lower()
        if not text: continue

        # 1) 부분일치
        for i, row in listings.iterrows():
            nm = row["name_l"]
            if len(nm) < min_len: continue
            if nm and nm in text:
                code = row["Code"]; key = row["Name"]
                counts.setdefault(key, {"code":code,"ticker":_kr_ticker(code), "hits":0,
                                        "sector":row["Sector"], "industry":row["Industry"]})
                counts[key]["hits"] += 1

        # 2) 유사도 보정
        tokens = [t for t in re.split(r"[^가-힣A-Za-z0-9]+", text) if len(t) >= min_len]
        for tok in set(tokens):
            for cand in difflib.get_close_matches(tok, names, n=3, cutoff=sim_cutoff):
                i = idx_by_name[cand]
                row = listings.iloc[i]
                code = row["Code"]; key = row["Name"]
                counts.setdefault(key, {"code":code,"ticker":_kr_ticker(code), "hits":0,
                                        "sector":row["Sector"], "industry":row["Industry"]})
                counts[key]["hits"] += 1
    return counts  # {회사명: {code,ticker,hits,sector,industry}}

def auto_build_theme_stocks(theme_rows, news_all, top_per_theme=6, extra_kws:dict|None=None):
    """
    뉴스 텍스트 ↔ KRX 상장사 자동 매핑, 테마 키워드를 업종/산업/회사명에 대조
    extra_kws: 테마 관리자에서 들어온 사용자 키워드(dict)
    """
    listings = load_krx_listings()
    mentions = extract_company_mentions(news_all, listings)
    # 테마별 후보 선별
    theme2stocks = {}
    for tr in theme_rows:
        theme = tr["theme"]
        theme_kw = theme.lower()
        user_kws = [k.lower() for k in (extra_kws or {}).get(theme, [])]
        candidates = []
        for name, meta in mentions.items():
            textblob = f"{name} {meta.get('sector','')} {meta.get('industry','')}".lower()
            ok = (theme_kw in textblob) or any(k in textblob for k in user_kws)
            if ok and meta.get("ticker"):
                candidates.append((name, meta["ticker"], meta["hits"]))
        # 언급수 내림차순
        candidates.sort(key=lambda x: x[2], reverse=True)
        # 중복 제거(티커 기준)
        seen=set(); uniq=[]
        for nm, tk, h in candidates:
            if tk in seen: continue
            seen.add(tk); uniq.append((nm, tk, h))
        theme2stocks[theme] = [(nm, tk) for nm, tk, _ in uniq[:top_per_theme]]
    return theme2stocks

# -------------------------
# 스타일 (티커바 + 카드 + 퀵메뉴 초소형)
# -------------------------
CSS = """
<style>
.ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
.ticker-track{display:flex;gap:12px;align-items:center;width:max-content;animation:ticker-scroll var(--speed,32s) linear infinite;}
@keyframes ticker-scroll{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.badge{display:inline-flex;align-items:center;gap:6px;background:#0f1420;border:1px solid #2b3a55;
  color:#c7d2fe;padding:4px 8px;border-radius:8px;font-weight:700;white-space:nowrap;font-size:0.9rem}
.badge .name{color:#9fb3c8;font-weight:600;}
.badge .up{color:#e66;} .badge .down{color:#6aa2ff;} .sep{color:#44526b;padding:0 4px;}
.small{font-size:.85rem;color:#9aa0a6}
.card-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 18px}
.stock-card{border:1px solid #263042;border-radius:10px;padding:10px;background:#0f1420}
.stock-card .nm{font-weight:700}
.stock-card .px{margin-top:3px}
.stock-card .px.up{color:#e66}
.stock-card .px.down{color:#6aa2ff}
.stock-card .px.flat{color:#a3aab8}
@media (max-width: 1000px){.card-grid{grid-template-columns:repeat(2,1fr)}}
.compact-item{margin-bottom:.45rem}
.compact-item .when{color:#9aa0a6;font-size:.85rem}
#MainMenu, footer {visibility:hidden;}
.quickbar{position:fixed;left:4px;top:24%;background:#0f1420;border:1px solid #2b3a55;border-radius:10px;
  padding:6px 6px; font-size:.72rem; z-index:9999; opacity:.80}
.quickbar a{display:block;color:#d0daee;text-decoration:none;margin:3px 0; padding:3px 6px; border-radius:6px;}
.quickbar a:hover{background:#14233a}
.section-h{scroll-margin-top:70px;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# -------------------------
# 헤더/티커바/새로고침
# -------------------------
st.markdown(f"#### 🧠 AI 뉴스리포트 — 업데이트: {now_kst_str()}")
if st.button("🔄 새로고침"): st.cache_data.clear(); st.rerun()

@st.cache_data(ttl=900)
def build_ticker_items():
    rows=[("KOSPI","^KS11",2),("KOSDAQ","^KQ11",2),
          ("DOW","^DJI",2),("NASDAQ","^IXIC",2),
          ("USD/KRW","KRW=X",2),("WTI","CL=F",2),
          ("Gold","GC=F",2),("Copper","HG=F",3)]
    items=[]
    for name,ticker,dp in rows:
        last, prev = fetch_quote(ticker)
        d=p=None
        if valid_prices(last, prev):
            d=last-prev; p=(d/prev)*100
        items.append({"name":name,"last":fmt_number(last,dp),
                      "pct":fmt_percent(p) if p is not None else "--",
                      "is_up":(d or 0)>0,"is_down":(d or 0)<0})
    return items

def render_ticker_line(items, speed_sec=32):
    chips=[]
    for it in items:
        arrow="▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        cls="up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(f"<span class='badge'><span class='name'>{it['name']}</span>{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>")
    line='<span class="sep">|</span>'.join(chips)
    st.markdown(f"<div class='ticker-wrap'><div class='ticker-track' style='--speed:{speed_sec}s'>{line}<span class='sep'>|</span>{line}</div></div>", unsafe_allow_html=True)

render_ticker_line(build_ticker_items())
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (지연 가능)")

# -------------------------
# 초소형 퀵메뉴
# -------------------------
st.markdown("""
<div class='quickbar'>
<a href='#sec-news'>📰 최신</a>
<a href='#sec-theme'>🔥 테마</a>
<a href='#sec-summary'>📑 요약</a>
<a href='#sec-prob'>📈 확률</a>
<a href='#sec-top'>🚀 Top5</a>
<a href='#sec-3d'>🔮 3일</a>
<a href='#sec-admin'>🛠 관리</a>
</div>
""", unsafe_allow_html=True)

# -------------------------
# 최신 뉴스 (제목 + 시간, 컴팩트)
# -------------------------
st.markdown('<div id="sec-news" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 📰 최신 뉴스 요약")
c1,c2 = st.columns([2,1])
with c1: cat = st.selectbox("📂 카테고리", list(CATEGORIES))
with c2: page = st.number_input("페이지", 1, 99, 1, 1)

news_all = fetch_category_news(cat, days=3, max_items=120)
pg = 10
chunk = news_all[(page-1)*pg : page*pg]
if not chunk:
    st.info("표시할 뉴스가 없습니다.")
else:
    for it in chunk:
        st.markdown(
            f"<div class='compact-item'>"
            f"<a href='{it['link']}' target='_blank'><b>{it['title']}</b></a><br>"
            f"<span class='when'>{it['time']}</span>"
            f"</div>", unsafe_allow_html=True
        )
st.caption(f"최근 3일 · {cat} · {len(news_all)}건 중 {(page-1)*pg+1}-{min(page*pg,len(news_all))} 표시")

# -------------------------
# 테마 키워드(기본) + 관리자 세션
# -------------------------
DEFAULT_THEME_KWS = {
    "AI":["ai","인공지능","챗봇","엔비디아","오픈ai","생성형","gpu"],
    "반도체":["반도체","hbm","칩","램","파운드리","소부장"],
    "로봇":["로봇","자율주행","협동로봇","amr","로보틱스"],
    "이차전지":["배터리","전고체","양극재","음극재","lfp"],
    "에너지":["에너지","정유","전력","태양광","풍력","가스","발전","전기요금"],
    "조선":["조선","선박","lng선","해운","수주"],
    "LNG":["lng","액화천연가스","가스공사","터미널"],
    "원전":["원전","smr","원자력","우라늄","정비"],
    "바이오":["바이오","제약","신약","임상","시밀러"],
}
if "CUSTOM_THEME_KWS" not in st.session_state:
    st.session_state.CUSTOM_THEME_KWS = {}     # {테마: [사용자 키워드]}
if "PINNED_STOCKS" not in st.session_state:
    st.session_state.PINNED_STOCKS = {}        # {테마: [(이름,티커), ...]}

def merged_theme_kws():
    merged = {k: list(set(v)) for k,v in DEFAULT_THEME_KWS.items()}
    for t, kws in st.session_state.CUSTOM_THEME_KWS.items():
        merged.setdefault(t, [])
        merged[t] = list(set(merged[t] + kws))
    return merged

# -------------------------
# 뉴스 기반 테마 감지
# -------------------------
st.markdown('<div id="sec-theme" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🔥 뉴스 기반 테마 요약")

def detect_themes(news_list, theme_kws:dict):
    counts = {t: 0 for t in theme_kws}
    sample = {t: "" for t in theme_kws}
    for n in news_list:
        text = (n.get("title","") + " " + n.get("desc","")).lower()
        for t, kws in theme_kws.items():
            if any(k in text for k in kws):
                counts[t] += 1
                if not sample[t]: sample[t] = n.get("link","")
    rows = []
    for t,c in counts.items():
        if c>0:
            rows.append({"theme":t,"count":int(c),"sample":sample[t]})
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows

# 전체 뉴스 3일치
news_cache = {k: fetch_category_news(k, 3, 120) for k in CATEGORIES}
all_news = []
for v in news_cache.values(): all_news.extend(v)

THEME_KEYWORDS = merged_theme_kws()
theme_rows = detect_themes(all_news, THEME_KEYWORDS)

if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다.")
else:
    st.markdown("**TOP 테마:** " + " ".join([f"🟢 {r['theme']}({r['count']})" for r in theme_rows[:5]]))
    df_theme = pd.DataFrame(theme_rows)
    # 링크 컬럼
    try:
        df_theme["샘플 뉴스"] = df_theme["sample"]
        st.dataframe(df_theme[["theme","count","샘플 뉴스"]].rename(columns={"theme":"테마","count":"뉴스건수"}),
                     use_container_width=True, hide_index=True,
                     column_config={"샘플 뉴스": st.column_config.LinkColumn("샘플 뉴스", display_text="열기")})
    except Exception:
        st.dataframe(df_theme.rename(columns={"theme":"테마","count":"뉴스건수"}), use_container_width=True, hide_index=True)

# -------------------------
# 자동 매핑으로 대표 종목 구성
# -------------------------
extra_kws = st.session_state.CUSTOM_THEME_KWS
auto_theme_stocks = auto_build_theme_stocks(theme_rows, all_news, top_per_theme=6, extra_kws=extra_kws)

st.markdown("### 🧩 대표 종목 시세 (자동 매핑 · 상승=빨강/하락=파랑)")
def rep_price(tk):
    l,p = fetch_quote(tk)
    if not valid_prices(l,p): return None, None, "flat"
    d = (l-p)/p*100
    tone = "up" if d>0 else ("down" if d<0 else "flat")
    return fmt_number(l,0), fmt_percent(d), tone

for tr in theme_rows[:5]:
    theme = tr["theme"]
    # 사용자 PINNED가 있으면 우선
    stocks = st.session_state.PINNED_STOCKS.get(theme) or auto_theme_stocks.get(theme, [])
    st.markdown(f"**{theme}**  <span class='small'>뉴스 {tr['count']}건</span>", unsafe_allow_html=True)
    if not stocks:
        st.caption("· 기사엔 테마가 많지만 종목명이 충분히 언급되지 않았습니다.")
        st.divider(); continue
    cards=[]
    for nm, tk in stocks[:6]:
        px, chg, tone = rep_price(tk)
        arrow = "▲" if tone=="up" else ("▼" if tone=="down" else "■")
        html = (f"<div class='stock-card'><div class='nm'>{nm}</div>"
                f"<div class='ticker'>{tk}</div>"
                f"<div class='px {tone}'>{px if px else '-'} {arrow if px else ''} {chg if px else ''}</div></div>")
        cards.append(html)
    st.markdown(f"<div class='card-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)
    st.divider()

# -------------------------
# AI 뉴스 요약엔진
# -------------------------
st.markdown('<div id="sec-summary" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 📑 AI 뉴스 요약엔진")

titles = [n["title"] for n in all_news]
words=[]
for t in titles:
    t = re.sub(r"[^가-힣A-Za-z0-9\s]"," ",t)
    words += [w for w in t.split() if len(w)>=2]
top_kw = [w for w,_ in Counter(words).most_common(10)]
st.write("📌 키워드:", ", ".join(top_kw) if top_kw else "-")

full_text = " ".join([n.get("title","")+" "+n.get("desc","") for n in all_news])
sentences = [s for s in re.split(r'[.!?]\s+', full_text) if len(s.strip())>20][:5]
if sentences:
    st.markdown(f"**요약:** {sentences[0][:140]}...")
    with st.expander("전체 요약문 보기 👇"):
        for s in sentences: st.markdown(f"- {s.strip()}")
else:
    st.info("요약 데이터를 가져오지 못했습니다.")

# -------------------------
# 테마별 상승 확률 리포트
# -------------------------
st.markdown('<div id="sec-prob" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 📈 AI 상승 확률 예측 리포트")

def calc_theme_strength(count, avg_delta):
    freq = min(count/20, 1.0)
    prc  = min(max((avg_delta+5)/10, 0), 1.0)
    return round((freq*0.6 + prc*0.4)*5, 1)

def calc_risk_level(avg_delta):
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

report=[]
for tr in theme_rows[:5]:
    theme = tr["theme"]
    deltas=[]
    for nm, tk in (auto_theme_stocks.get(theme, [])[:6]):
        l,p = fetch_quote(tk)
        if valid_prices(l,p): deltas.append((l-p)/p*100)
    avg = float(np.mean(deltas)) if deltas else 0.0
    report.append({"테마":theme,"뉴스건수":tr["count"],"평균등락(%)":round(avg,2),
                   "테마강도(1~5)":calc_theme_strength(tr["count"],avg),
                   "리스크레벨(1~5)":calc_risk_level(avg)})
st.dataframe(pd.DataFrame(report), use_container_width=True, hide_index=True)

# -------------------------
# 유망 종목 Top5
# -------------------------
st.markdown('<div id="sec-top" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🚀 오늘의 AI 유망 종목 Top5")

def pick_promising_stocks(theme_rows, top_n=5):
    cands=[]
    for tr in theme_rows[:8]:
        theme = tr["theme"]
        for name, tk in auto_theme_stocks.get(theme, []):
            l,p = fetch_quote(tk)
            if not valid_prices(l,p): continue
            delta = (l-p)/p*100
            score = tr["count"]*0.3 + delta*0.7
            cands.append({"테마":theme,"종목명":name,"티커":tk,
                          "등락률(%)":round(delta,2),"뉴스빈도":tr["count"],"AI점수":round(score,2)})
    df = pd.DataFrame(cands)
    return df.sort_values("AI점수", ascending=False).head(top_n) if not df.empty else df

recommend_df = pick_promising_stocks(theme_rows, 5)
if recommend_df.empty:
    st.info("추천할 종목이 없습니다.")
else:
    st.dataframe(recommend_df, use_container_width=True, hide_index=True)
    st.markdown("### 🧾 AI 종합 판단")
    for _, r in recommend_df.iterrows():
        emoji = "🔺" if r["등락률(%)"]>0 else "🔻"
        st.markdown(f"- **{r['종목명']} ({r['티커']})** — 테마: *{r['테마']}*, "
                    f"등락률 **{r['등락률(%)']}%**, 뉴스빈도 {r['뉴스빈도']}건, AI점수 {r['AI점수']}")

# -------------------------
# 3일 예측 모듈
# -------------------------
st.markdown('<div id="sec-3d" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🔮 AI 3일 예측: 내일 오를 확률")

@st.cache_data(ttl=900)
def load_hist(ticker: str, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    return df[~df.index.duplicated(keep='last')].dropna()

def rsi(series: pd.Series, period: int = 14):
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean().replace(0, np.nan)
    rs = roll_up / roll_down
    r = 100 - (100 / (1 + rs))
    return r.fillna(50)

def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    line = ema_f - ema_s
    sig  = line.ewm(span=signal, adjust=False).mean()
    hist = line - sig
    return line, sig, hist

def build_features(df: pd.DataFrame):
    price = df["Close"]
    feat = pd.DataFrame(index=df.index)
    feat["ret_1d"] = price.pct_change(1)
    feat["ret_5d"] = price.pct_change(5)
    feat["ret_10d"] = price.pct_change(10)
    feat["vol_5d"] = price.pct_change().rolling(5).std()
    feat["vol_20d"] = price.pct_change().rolling(20).std()
    feat["rsi_14"] = rsi(price, 14)
    m, s, h = macd(price)
    feat["macd"] = m; feat["macd_sig"] = s; feat["macd_hist"] = h
    ma5 = price.rolling(5).mean(); ma20 = price.rolling(20).mean()
    feat["ma5_gap"] = (price-ma5)/ma5
    feat["ma20_gap"] = (price-ma20)/ma20
    y = (price.shift(-1) > price).astype(int)
    return pd.concat([feat, y.rename("y")], axis=1).dropna()

def fit_predict_prob(df_feat: pd.DataFrame):
    if len(df_feat) < 120: return None, None
    data = df_feat.tail(300)
    X = data.drop(columns=["y"]).values
    y = data["y"].values
    n = len(data); split = max(60, n-3)
    X_train, y_train = X[:split], y[:split]
    X_pred = X[split:]
    model = LogisticRegression(max_iter=300)
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_pred)[:,1]
    p1 = float(prob[0]) if len(prob)>0 else None
    p3 = float(prob.mean()) if len(prob)>0 else None
    return p1, p3

rows=[]
if recommend_df.empty:
    st.info("먼저 Top5가 생성되어야 예측을 수행할 수 있어요.")
else:
    with st.spinner("예측 계산 중..."):
        for _, r in recommend_df.iterrows():
            name, tk = r["종목명"], r["티커"]
            try:
                feats = build_features(load_hist(tk))
                p1, p3 = fit_predict_prob(feats)
                if p1 is None:
                    rows.append({"종목명":name,"티커":tk,"내일상승확률":"-","3일평균확률":"-","신호":"데이터부족"})
                else:
                    sig = "매수관심" if p1>=0.55 else ("관망" if p1>=0.45 else "주의")
                    rows.append({"종목명":name,"티커":tk,"내일상승확률":round(p1*100,1),
                                 "3일평균확률":round(p3*100,1),"신호":sig})
            except Exception:
                rows.append({"종목명":name,"티커":tk,"내일상승확률":"-","3일평균확률":"-","신호":"오류"})

pred_df = pd.DataFrame(rows)
if not pred_df.empty:
    def _prob_color(v):
        try: v=float(v)
        except: return ""
        if v>=60: return "background-color: rgba(217,48,37,.18); color:#ffd2cf; font-weight:700;"
        if v>=50: return "background-color: rgba(255,193,7,.12);"
        return "background-color: rgba(26,115,232,.14); color:#d7e6ff;"
    st.dataframe(pred_df.style.map(_prob_color, subset=["내일상승확률","3일평균확률"]),
                 use_container_width=True, hide_index=True)
    st.markdown("### 🧠 AI 인사이트")
    for _, row in pred_df.iterrows():
        if row["내일상승확률"] == "-":
            st.markdown(f"- **{row['종목명']} ({row['티커']})** — 데이터 부족/오류")
        else:
            arrow = "🔺" if row["내일상승확률"]>=50 else "🔻"
            st.markdown(f"- **{row['종목명']} ({row['티커']})** — 내일 상승 확률 **{row['내일상승확률']}%** "
                        f"(3일 평균 {row['3일평균확률']}%), 신호 **{row['신호']}** {arrow}")

# -------------------------
# 테마 관리자 (작게)
# -------------------------
st.markdown('<div id="sec-admin" class="section-h"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🛠 테마 관리자 (키워드/핀 고정 저장)")

with st.form("theme_admin", clear_on_submit=False):
    st.markdown("### 테마 키워드 추가")
    t1 = st.text_input("테마명 (예: 전력)")
    kw = st.text_input("키워드(콤마구분, 예: 전력, 한전, 전기요금)")
    st.markdown("---")
    st.markdown("### 대표 종목 핀 고정 (테마에 우선 적용)")
    t2 = st.text_input("테마명(핀 고정용)")
    st.markdown("이름|티커 한 줄씩 (예: 한국전력|015760.KS)")
    pin_txt = st.text_area("핀 목록", height=90, placeholder="한국전력|015760.KS\n한전KPS|051600.KS")
    ok = st.form_submit_button("💾 저장")

    if ok:
        if t1.strip():
            kws = [x.strip() for x in kw.split(",") if x.strip()]
            st.session_state.CUSTOM_THEME_KWS.setdefault(t1, [])
            st.session_state.CUSTOM_THEME_KWS[t1] = list(set(st.session_state.CUSTOM_THEME_KWS[t1] + kws))
            st.success(f"테마 키워드 저장: {t1} → {', '.join(kws) if kws else '-'}")
        if t2.strip():
            pairs=[]
            for ln in [l.strip() for l in pin_txt.splitlines() if "|" in l]:
                nm, tk = ln.split("|",1)
                nm, tk = nm.strip(), tk.strip()
                if nm and tk: pairs.append((nm, tk))
            st.session_state.PINNED_STOCKS[t2] = pairs
            st.success(f"핀 고정 저장: {t2} → {len(pairs)}개")

if st.session_state.CUSTOM_THEME_KWS:
    st.caption("**추가된 키워드**")
    for k,v in st.session_state.CUSTOM_THEME_KWS.items():
        st.write(f"- {k}: {', '.join(v)}")
if st.session_state.PINNED_STOCKS:
    st.caption("**핀 고정 종목**")
    for k,v in st.session_state.PINNED_STOCKS.items():
        st.write(f"- {k}: {', '.join([f'{n}({t})' for n,t in v])}")
