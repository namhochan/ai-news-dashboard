# -*- coding: utf-8 -*-
# app.py
import math, re
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

KST = ZoneInfo("Asia/Seoul")

# =========================
# 공통 설정 & 유틸
# =========================
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")

def now_kst():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)")

def fmt_number(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def fmt_percent(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

def valid_prices(last, prev):
    return last is not None and prev not in (None, 0) and all(map(np.isfinite, [last, prev]))

# =========================
# 시세 수집 (안정형)
# =========================
@st.cache_data(ttl=600)
def fetch_quote(ticker: str):
    # 1) fast_info
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if valid_prices(last, prev):
            return float(last), float(prev)
    except Exception:
        pass
    # 2) 최근 7일 종가
    try:
        df = yf.download(ticker, period="7d", interval="1d", auto_adjust=False, progress=False)
        closes = df.get("Close")
        if closes is None:
            return None, None
        closes = closes.dropna()
        if len(closes) == 0:
            return None, None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# =========================
# 뉴스 (Google RSS)
# =========================
def clean_html(raw): return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days):
    now = datetime.now(KST)
    out = []
    for e in feed.entries:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            pub = datetime(*e.updated_parsed[:6], tzinfo=KST)
        if pub and (now - pub) > timedelta(days=days):
            continue
        title = getattr(e, "title", "").strip()
        link = getattr(e, "link", "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
        desc = clean_html(getattr(e, "summary", ""))
        out.append({"title": title, "link": link,
                    "time": pub.strftime("%Y-%m-%d %H:%M") if pub else "-",
                    "desc": desc})
    return out

@st.cache_data(ttl=600)
def fetch_google_news_by_keyword(keyword, days=3, limit=50):
    q = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    return _parse_entries(feed, days)[:limit]

CATEGORIES = {
    "경제뉴스": ["경제","금리","물가","환율","성장률","무역"],
    "주식뉴스": ["코스피","코스닥","증시","주가","외국인 매수","기관 매도"],
    "산업뉴스": ["반도체","AI","배터리","자동차","로봇","수출입","전력","전기요금","전력수급"],
    "정책뉴스": ["정책","정부","예산","규제","세금","산업부"],
}

@st.cache_data(ttl=600)
def fetch_category_news(cat, days=3, max_items=120):
    seen, out = set(), []
    for kw in CATEGORIES.get(cat, []):
        try:
            for it in fetch_google_news_by_keyword(kw, days):
                k = (it["title"], it["link"])
                if k in seen: 
                    continue
                seen.add(k)
                out.append(it)
        except Exception:
            continue
    def _key(x):
        try: return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except: return datetime.min
    out.sort(key=_key, reverse=True)
    return out[:max_items]

# =========================
# 티커바
# =========================
TICKER_CSS = """
<style>
.ticker-wrap{position:relative;overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420;}
.ticker-track{display:flex;gap:12px;align-items:center;width:max-content;will-change:transform;
  animation:ticker-scroll var(--speed,32s) linear infinite;}
@keyframes ticker-scroll{0%{transform:translateX(0);}100%{transform:translateX(-50%);}}
.badge{display:inline-flex;align-items:center;gap:6px;background:#0f1420;border:1px solid #2b3a55;
  color:#c7d2fe;padding:4px 8px;border-radius:8px;font-weight:700;white-space:nowrap;font-size:0.9rem}
.badge .name{color:#9fb3c8;font-weight:600;}
.badge .up{color:#e66;} .badge .down{color:#6aa2ff;} .sep{color:#44526b;padding:0 4px;}
.small-cap{font-size:.85rem;color:#9aa0a6}
.card-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:8px 0 18px}
.stock-card{border:1px solid #263042;border-radius:10px;padding:10px;background:#0f1420}
.stock-card .nm{font-weight:700}
.stock-card .px{margin-top:3px}
.stock-card .px.up{color:#e66}
.stock-card .px.down{color:#6aa2ff}
.stock-card .px.flat{color:#a3aab8}
@media (max-width: 1000px){.card-grid{grid-template-columns:repeat(2,1fr)}}
.quick-menu{position:fixed;right:8px;top:90px;z-index:9999;width:170px}
.quick-menu .box{background:#0f1420;border:1px solid #2b3a55;border-radius:14px;padding:8px}
.quick-menu a{display:flex;align-items:center;gap:6px;font-size:.86rem;padding:6px 8px;margin:4px 0;
  border:1px solid #283652;border-radius:10px;text-decoration:none;color:#dbe6ff}
.quick-menu a:hover{background:#12223b}
.quick-title{font-size:.9rem;color:#98a6be;margin:2px 0 8px 2px}
.section-h{scroll-margin-top:70px;}
.compact-item{margin-bottom:.45rem}
.compact-item .when{color:#9aa0a6;font-size:.85rem}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

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
            d = last - prev
            p = (d/prev)*100
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

# =========================
# 헤더 + 퀵 메뉴(작게)
# =========================
st.markdown(f"#### 🧠 AI 뉴스리포트 — 업데이트: {now_kst()}")
rc1, rc2 = st.columns([1,5])
with rc1: st.markdown("### 📊 오늘의 시장 요약")
with rc2:
    if st.button("🔄 새로고침", use_container_width=False):
        st.cache_data.clear()
        st.rerun()
render_ticker_line(build_ticker_items())

# 작은 퀵메뉴
quick = """
<div class="quick-menu">
  <div class="box">
    <div class="quick-title">Quick Menu</div>
    <a href="#sec-news">📰 최신 요약</a>
    <a href="#sec-theme">🔥 테마 요약</a>
    <a href="#sec-engine">🧠 요약엔진</a>
    <a href="#sec-prob">📊 상승 확률</a>
    <a href="#sec-top">🚀 Top5</a>
    <a href="#sec-3d">🔮 3일 예측</a>
    <a href="#sec-admin">🛠 테마 관리자</a>
  </div>
</div>
"""
st.markdown(quick, unsafe_allow_html=True)

st.caption("※ 상승=빨강, 하락=파랑 · 가격: Yahoo Finance (지연 가능)")

# =========================
# 최신 뉴스 (제목 + 시간, 컴팩트)
# =========================
st.markdown('<div id="sec-news" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 📰 최신 뉴스 요약")

c1, c2 = st.columns([2,1])
with c1: cat = st.selectbox("📂 카테고리", list(CATEGORIES))
with c2: page = st.number_input("페이지", 1, 99, 1, 1)
news_all = fetch_category_news(cat, days=3, max_items=120)

pg_size = 10
start = (page-1)*pg_size
chunk = news_all[start:start+pg_size]

if not chunk:
    st.info("표시할 뉴스가 없습니다.")
else:
    for it in chunk:
        st.markdown(
            f"<div class='compact-item'>"
            f"<a href='{it['link']}' target='_blank'><b>{it['title']}</b></a><br>"
            f"<span class='when'>{it['time']}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
st.caption(f"최근 3일 · {cat} · {len(news_all)}건 중 {start+1}-{min(start+pg_size, len(news_all))} 표시")

# =========================
# 테마 키워드 & 대표 종목 맵
# =========================
THEME_KEYWORDS = {
    "AI":["ai","인공지능","챗봇","엔비디아","오픈ai","생성형"],
    "반도체":["반도체","hbm","칩","램","파운드리"],
    "로봇":["로봇","자율주행","협동로봇","amr"],
    "이차전지":["배터리","전고체","양극재","음극재","lfp"],
    "에너지":["에너지","정유","전력","태양광","풍력","가스"],
    "조선":["조선","선박","lng선","해운"],
    "LNG":["lng","가스공사","터미널"],
    "원전":["원전","smr","원자력","우라늄"],
    "바이오":["바이오","제약","신약","임상"],
}
THEME_STOCKS = {
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

# =========================
# 뉴스 기반 테마 요약 (오류 수정 버전)
# =========================
st.markdown('<div id="sec-theme" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

def detect_themes_hybrid(news_list, theme_kws:dict, price_boost=True, pct_threshold=2.0, min_stocks=2):
    counts = {t: 0 for t in theme_kws}
    sample = {t: "" for t in theme_kws}

    for n in news_list:
        text = (n.get("title","") + " " + n.get("desc","")).lower()
        for t, kws in theme_kws.items():
            if any(k in text for k in kws):
                counts[t] += 1
                if not sample[t]:
                    sample[t] = n.get("link","")

    price_info = {}
    for theme, stocks in THEME_STOCKS.items():
        deltas = []
        for _, tk in stocks:
            last, prev = fetch_quote(tk)
            if valid_prices(last, prev):
                deltas.append((last - prev) / prev * 100.0)
        avg_delta = float(np.mean(deltas)) if deltas else 0.0
        up_cnt = int(sum(d > 0 for d in deltas))
        price_info[theme] = (avg_delta, up_cnt)
        if price_boost and avg_delta >= pct_threshold and up_cnt >= min_stocks:
            counts[theme] = max(counts.get(theme, 0), 1)

    rows = []
    all_themes = set(theme_kws.keys()) | set(THEME_STOCKS.keys())
    for theme in all_themes:
        c = int(counts.get(theme, 0))
        avg_delta, up_cnt = price_info.get(theme, (0.0, 0))
        if c > 0 or (price_boost and avg_delta >= pct_threshold and up_cnt >= min_stocks):
            driver = ("가격 주도" if (c == 0 and avg_delta >= pct_threshold and up_cnt >= min_stocks)
                      else ("뉴스+가격" if (c > 0 and avg_delta >= pct_threshold) else
                            ("뉴스 주도" if c > 0 else "가격 주도")))
            rows.append({
                "테마": theme,
                "뉴스건수": c,
                "평균등락(%)": round(avg_delta, 2),
                "상승종목수": int(up_cnt),
                "주도요인": driver,
                "샘플링크": sample.get(theme, "") or "",
                "대표종목": " · ".join([nm for nm, _ in THEME_STOCKS.get(theme, [])]) or "-",
            })
    rows.sort(key=lambda x: (x["뉴스건수"], x["평균등락(%)"]), reverse=True)
    return rows

# 올바르게 뉴스 합치기 (NULL 출력 방지)
news_cache = {k: fetch_category_news(k, 3, 120) for k in CATEGORIES}
all_news = []
for v in news_cache.values():
    all_news.extend(v)

theme_rows = detect_themes_hybrid(all_news, THEME_KEYWORDS, True, 2.0, 2)

if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다.")
else:
    df_theme = pd.DataFrame(theme_rows)
    df_view = df_theme.copy()
    df_view["샘플 뉴스"] = df_view["샘플링크"]

    try:
        st.dataframe(
            df_view[["테마","뉴스건수","평균등락(%)","상승종목수","주도요인","대표종목","샘플 뉴스"]],
            use_container_width=True, hide_index=True,
            column_config={"샘플 뉴스": st.column_config.LinkColumn("샘플 뉴스", display_text="열기")}
        )
    except Exception:
        st.dataframe(df_view, use_container_width=True, hide_index=True)
        st.caption("※ ‘샘플 뉴스’ 컬럼의 URL을 클릭해 열어주세요.")

    st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")
    def rep_price(tk):
        last, prev = fetch_quote(tk)
        if not valid_prices(last, prev): return None, None, "flat"
        delta = (last - prev) / prev * 100
        tone = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        return fmt_number(last, 0), fmt_percent(delta), tone

    for tr in df_theme.head(5).to_dict("records"):
        theme = tr["테마"]
        stocks = THEME_STOCKS.get(theme, [])[:6]
        if not stocks: 
            continue
        st.markdown(
            f"**{theme}** — "
            f"<span class='small-cap'>주도: {tr['주도요인']} · 평균등락 {tr['평균등락(%)']}%</span>",
            unsafe_allow_html=True
        )
        cards=[]
        for nm, tk in stocks:
            px, chg, tone = rep_price(tk)
            arrow = "▲" if tone=="up" else ("▼" if tone=="down" else "■")
            html = (f"<div class='stock-card'><div class='nm'>{nm}</div>"
                    f"<div class='ticker'>{tk}</div>"
                    f"<div class='px {tone}'>{px if px else '-'} {arrow if px else ''} {chg if px else ''}</div></div>")
            cards.append(html)
        st.markdown(f"<div class='card-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)

# =========================
# AI 뉴스 요약엔진 (더보기)
# =========================
st.markdown('<div id="sec-engine" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🧠 AI 뉴스 요약엔진")
titles = [n["title"] for n in all_news]
words=[]
for t in titles:
    t = re.sub(r"[^가-힣A-Za-z0-9\s]"," ",t)
    words += [w for w in t.split() if len(w)>=2]
top_kw = [w for w,_ in Counter(words).most_common(10)]
st.markdown("### 📌 핵심 키워드 TOP10")
st.write(", ".join(top_kw) if top_kw else "데이터 부족")

full_text = " ".join([n.get("title","")+" "+n.get("desc","") for n in all_news])
sentences = [s for s in re.split(r'[.!?]\s+', full_text) if len(s.strip())>20][:5]
st.markdown("### 📰 핵심 요약문")
if sentences:
    st.markdown(f"**요약:** {sentences[0][:150]}...")
    with st.expander("전체 요약문 보기 👇"):
        for s in sentences: st.markdown(f"- {s.strip()}")
else:
    st.info("요약 데이터를 가져오지 못했습니다.")

# =========================
# AI 상승 확률 리포트
# =========================
st.markdown('<div id="sec-prob" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 📊 AI 상승 확률 예측 리포트")

def calc_theme_strength(count, avg_delta):
    freq = min(count/20, 1.0)
    prc = min(max((avg_delta+5)/10, 0), 1.0)
    return round((freq*0.6 + prc*0.4)*5, 1)

def calc_risk_level(avg_delta):
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

report=[]
for tr in theme_rows[:5]:
    theme = tr["테마"]
    deltas=[]
    for _, tk in THEME_STOCKS.get(theme, []):
        last, prev = fetch_quote(tk)
        if valid_prices(last, prev):
            deltas.append((last-prev)/prev*100)
    avg_delta = float(np.mean(deltas)) if deltas else 0.0
    report.append({
        "테마": theme,
        "뉴스건수": tr["뉴스건수"],
        "평균등락(%)": round(avg_delta,2),
        "테마강도(1~5)": calc_theme_strength(tr["뉴스건수"], avg_delta),
        "리스크레벨(1~5)": calc_risk_level(avg_delta)
    })

st.dataframe(pd.DataFrame(report), use_container_width=True, hide_index=True)
st.caption("※ 테마강도↑ = 뉴스+가격 활발 / 리스크레벨↑ = 변동성·하락 가능성 높음")

# =========================
# 유망 종목 Top5
# =========================
st.markdown('<div id="sec-top" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🚀 오늘의 AI 유망 종목 Top5")

def pick_promising_stocks(theme_rows, top_n=5):
    cands=[]
    for tr in theme_rows[:8]:
        theme = tr["테마"]
        for name, tk in THEME_STOCKS.get(theme, []):
            last, prev = fetch_quote(tk)
            if not valid_prices(last, prev): 
                continue
            delta = (last-prev)/prev*100
            score = tr["뉴스건수"]*0.3 + delta*0.7
            cands.append({"테마":theme,"종목명":name,"티커":tk,
                          "등락률(%)":round(delta,2),"뉴스빈도":tr["뉴스건수"],"AI점수":round(score,2)})
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

# =========================
# 3일 예측 모듈
# =========================
st.markdown('<div id="sec-3d" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🔮 AI 3일 예측: 내일 오를 확률")

@st.cache_data(ttl=600)
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
    sig = line.ewm(span=signal, adjust=False).mean()
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
    model = LogisticRegression(max_iter=300, n_jobs=None)
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
                hist = load_hist(tk)
                feats = build_features(hist)
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

# =========================
# 테마 관리자 (간단한 추가/저장)
# =========================
st.markdown('<div id="sec-admin" class="section-h"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🛠 테마 관리자")

if "custom_themes" not in st.session_state:
    st.session_state.custom_themes = {}

with st.form("theme_form", clear_on_submit=False):
    st.markdown("### 새 테마/키워드/종목 추가")
    new_theme = st.text_input("테마명 (예: 전력)")
    kw_text   = st.text_input("키워드 콤마구분 (예: 전력, 한전, 전기요금)")
    st.markdown("종목은 ‘이름|티커’ 한 줄씩 (예: 한국전력|015760.KS)")
    stock_text = st.text_area("대표 종목 목록", height=100)
    save = st.form_submit_button("💾 저장")
    if save and new_theme.strip():
        kws = [k.strip() for k in kw_text.split(",") if k.strip()]
        lines = [l.strip() for l in stock_text.splitlines() if "|" in l]
        pairs=[]
        for ln in lines:
            nm, tk = ln.split("|", 1)
            nm, tk = nm.strip(), tk.strip()
            if nm and tk:
                pairs.append((nm, tk))
        if kws:
            THEME_KEYWORDS[new_theme] = list(set(THEME_KEYWORDS.get(new_theme, []) + kws))
        if pairs:
            THEME_STOCKS[new_theme] = list({p[1]:p for p in (THEME_STOCKS.get(new_theme, []) + pairs)}.values())
        st.session_state.custom_themes[new_theme] = {"keywords":kws, "stocks":pairs}
        st.success(f"'{new_theme}' 저장 완료!")

if st.session_state.custom_themes:
    st.markdown("### 현재 추가된 테마")
    for t, v in st.session_state.custom_themes.items():
        st.write(f"- **{t}** / 키워드: {', '.join(v['keywords']) or '-'} / 종목: {', '.join([f'{n}({k})' for n,k in v['stocks']]) or '-'}")

st.caption("※ 캐시에 저장됩니다. 코드/레포에 영구 저장하려면 수동 반영해주세요.")
