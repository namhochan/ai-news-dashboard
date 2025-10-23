
# -*- coding: utf-8 -*-
"""
AI 뉴스리포트 – 풀버전 (오류수정/최적화)
- 지수/환율/원자재 티커바(자동 스크롤)
- 최신 뉴스(3일) 크롤링 + 페이지
- 테마 관리자(키워드/종목 UI 저장: themes.json + (선택) GitHub 커밋)
- 뉴스+가격 하이브리드 테마 감지
- 대표종목 시세 카드, AI 요약/키워드
- 테마 강도 리포트, 유망 종목 Top5
- 3일 예측(로지스틱)
"""

import math, re, json, base64
from pathlib import Path
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

# =========================================
# 기본 설정
# =========================================
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")
st.markdown(f"<small>업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}</small>", unsafe_allow_html=True)

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

# =========================================
# 테마 저장/로드 (동적 설정)
# =========================================
THEME_STORE_PATH = Path("themes.json")

DEFAULT_THEME_CFG = {
    "AI": {
        "keywords": ["ai", "인공지능", "생성형", "챗봇", "엔비디아", "오픈ai", "gpu"],
        "stocks": [
            {"name":"삼성전자","ticker":"005930.KS"},
            {"name":"네이버","ticker":"035420.KS"},
            {"name":"카카오","ticker":"035720.KS"},
        ],
    },
    "반도체": {
        "keywords": ["반도체","hbm","메모리","파운드리","칩","램","소부장"],
        "stocks": [
            {"name":"SK하이닉스","ticker":"000660.KS"},
            {"name":"DB하이텍","ticker":"000990.KS"},
            {"name":"리노공업","ticker":"058470.KQ"},
        ],
    },
    "로봇": {
        "keywords": ["로봇","자율주행","협동로봇","amr","로보틱스"],
        "stocks": [
            {"name":"레인보우로보틱스","ticker":"277810.KQ"},
            {"name":"유진로봇","ticker":"056080.KQ"},
            {"name":"티로보틱스","ticker":"117730.KQ"},
            {"name":"로보스타","ticker":"090360.KQ"},
        ],
    },
    "이차전지": {
        "keywords": ["배터리","이차전지","전고체","양극재","음극재","lfp"],  # lfp로 수정
        "stocks": [
            {"name":"LG에너지솔루션","ticker":"373220.KS"},
            {"name":"포스코퓨처엠","ticker":"003670.KS"},
            {"name":"에코프로","ticker":"086520.KQ"},
        ],
    },
    "에너지": {
        "keywords": ["에너지","정유","전력","태양광","풍력","가스"],
        "stocks": [
            {"name":"한국전력","ticker":"015760.KS"},
            {"name":"두산에너빌리티","ticker":"034020.KS"},
            {"name":"한화솔루션","ticker":"009830.KS"},
        ],
    },
    "전력": {
        "keywords": ["전력","송전","배전","송배전","전력망","hvdc","한국전력","한전kps","한전기술","전선","케이블"],
        "stocks": [
            {"name":"한국전력","ticker":"015760.KS"},
            {"name":"한전KPS","ticker":"051600.KS"},
            {"name":"한전기술","ticker":"052690.KS"},
            {"name":"대한전선","ticker":"001440.KS"},
            {"name":"LS ELECTRIC","ticker":"010120.KS"},
        ],
    },
    "조선": {
        "keywords": ["조선","선박","lng선","해운"],
        "stocks": [
            {"name":"HD한국조선해양","ticker":"009540.KS"},
            {"name":"HD현대미포","ticker":"010620.KS"},
            {"name":"한화오션","ticker":"042660.KS"},
            {"name":"삼성중공업","ticker":"010140.KS"},
        ],
    },
    "원전": {
        "keywords": ["원전","smr","원자력","우라늄"],
        "stocks": [
            {"name":"두산에너빌리티","ticker":"034020.KS"},
            {"name":"우진","ticker":"105840.KQ"},
            {"name":"한전KPS","ticker":"051600.KS"},
            {"name":"보성파워텍","ticker":"006910.KQ"},
        ],
    },
    "바이오": {
        "keywords": ["바이오","제약","신약","임상"],
        "stocks": [
            {"name":"셀트리온","ticker":"068270.KS"},
            {"name":"에스티팜","ticker":"237690.KQ"},
            {"name":"알테오젠","ticker":"196170.KQ"},
            {"name":"메디톡스","ticker":"086900.KQ"},
        ],
    },
}

def load_theme_config() -> dict:
    if THEME_STORE_PATH.exists():
        try:
            return json.loads(THEME_STORE_PATH.read_text(encoding="utf-8"))
        except Exception:
            st.warning("themes.json 읽기 실패 — 기본값으로 초기화합니다.")
    return DEFAULT_THEME_CFG.copy()

def save_theme_config(cfg: dict):
    THEME_STORE_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def push_to_github_file(cfg: dict) -> bool:
    """(선택) Secrets에 토큰 정보가 있으면 themes.json을 GitHub에 커밋"""
    try:
        token = st.secrets.get("GITHUB_TOKEN")
        repo  = st.secrets.get("THEME_REPO")
        path  = st.secrets.get("THEME_PATH", "themes.json")
        if not token or not repo:
            return False
        import requests  # requirements.txt에 포함
        api = f"https://api.github.com/repos/{repo}/contents/{path}"
        r = requests.get(api, headers={"Authorization": f"token {token}"})
        sha = r.json().get("sha") if r.status_code == 200 else None
        content = json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8")
        payload = {"message": "chore: update themes.json from Streamlit UI",
                   "content": base64.b64encode(content).decode("utf-8")}
        if sha: payload["sha"] = sha
        r2 = requests.put(api, headers={"Authorization": f"token {token}"}, json=payload)
        return r2.status_code in (200, 201)
    except Exception:
        return False

def cfg_to_maps(cfg: dict):
    kws_map = {t: v.get("keywords", []) for t, v in cfg.items()}
    stocks_map = {t: [(s["name"], s["ticker"]) for s in v.get("stocks", [])] for t, v in cfg.items()}
    return kws_map, stocks_map

if "theme_cfg" not in st.session_state:
    st.session_state.theme_cfg = load_theme_config()
THEME_KEYWORDS, THEME_STOCKS = cfg_to_maps(st.session_state.theme_cfg)

# =========================================
# 공통 방어/캐시
# =========================================
def valid_prices(last, prev):
    if last is None or prev in (None, 0):
        return False
    try:
        if isinstance(last, float) and (math.isnan(last) or math.isinf(last)):
            return False
        if isinstance(prev, float) and (math.isnan(prev) or math.isinf(prev)):
            return False
    except Exception:
        pass
    return True

# =========================================
# 시세 수집
# =========================================
def fetch_quote(ticker: str):
    """fast_info → 실패 시 7일/일봉 대체"""
    try:
        t = yf.Ticker(ticker)
        last, prev = getattr(t.fast_info, "last_price", None), getattr(t.fast_info, "previous_close", None)
        if valid_prices(last, prev):
            return float(last), float(prev)
    except Exception:
        pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        c = df.get("Close")
        if c is None or c.dropna().empty:
            return None, None
        c = c.dropna()
        last = float(c.iloc[-1])
        prev = float(c.iloc[-2]) if len(c) >= 2 else None
        return (last, prev) if valid_prices(last, prev) else (None, None)
    except Exception:
        return None, None

# =========================================
# 뉴스 수집 (Google RSS)
# =========================================
def clean_html(raw):
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days):
    now = datetime.now(KST)
    out = []
    for e in feed.entries:
        t = None
        if getattr(e, "published_parsed", None):
            t = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            t = datetime(*e.updated_parsed[:6], tzinfo=KST)
        if t and (now - t) > timedelta(days=days):
            continue
        title, link = e.get("title", "").strip(), e.get("link", "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
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
    "산업뉴스": ["반도체","AI","배터리","자동차","로봇","수출입","전력","HVDC"],
    "정책뉴스": ["정책","정부","예산","규제","세금","산업부"],
}

def fetch_category_news(cat, days=3, max_items=100):
    seen, out = set(), []
    for kw in CATEGORIES.get(cat, []):
        try:
            for it in fetch_google_news_by_keyword(kw, days):
                k = (it["title"], it["link"])
                if k in seen: 
                    continue
                seen.add(k); out.append(it)
        except Exception:
            continue
    def key(x):
        try: return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except: return datetime.min
    return sorted(out, key=key, reverse=True)[:max_items]

@st.cache_data(ttl=600)
def load_all_news_3days() -> dict:
    data = {}
    for c in CATEGORIES:
        data[c] = fetch_category_news(c, 3, 100)
    return data

news_cache = load_all_news_3days()

# =========================================
# 티커바
# =========================================
def build_ticker_items():
    rows=[("KOSPI","^KS11",2),("KOSDAQ","^KQ11",2),
          ("DOW","^DJI",2),("NASDAQ","^IXIC",2),
          ("USD/KRW","KRW=X",2),("WTI","CL=F",2),
          ("Gold","GC=F",2),("Copper","HG=F",3)]
    items=[]
    for name,ticker,dp in rows:
        last, prev = fetch_quote(ticker)
        d, p = None, None
        if valid_prices(last, prev):
            d = last - prev
            p = (d / prev) * 100
        items.append({
            "name": name,
            "last": fmt_number(last, dp),
            "pct": fmt_percent(p) if p is not None else "--",
            "is_up": (d or 0) > 0,
            "is_down": (d or 0) < 0
        })
    return items

TICKER_CSS = """
<style>
.ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420}
.ticker-track{display:flex;gap:16px;align-items:center;width:max-content;will-change:transform;animation:ticker-scroll var(--speed,30s) linear infinite}
@keyframes ticker-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.badge{display:inline-flex;align-items:center;gap:8px;background:#0f1420;border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap}
.badge .name{color:#9fb3c8;font-weight:600}
.badge .up{color:#e66}.badge .down{color:#6aa2ff}.sep{color:#44526b;padding:0 6px}
</style>
"""
st.markdown(TICKER_CSS, unsafe_allow_html=True)

def render_ticker_line(items, speed_sec=30):
    chips=[]
    for it in items:
        arrow="▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
        cls="up" if it["is_up"] else ("down" if it["is_down"] else "")
        chips.append(f"<span class='badge'><span class='name'>{it['name']}</span>{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>")
    line='<span class="sep">|</span>'.join(chips)
    html=f"<div class='ticker-wrap' style='--speed:{speed_sec}s'><div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>"
    st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
    col1,col2=st.columns([1,5])
    with col1: st.markdown("### 📊 오늘의 시장 요약")
    with col2:
        if st.button("🔄 새로고침"):
            st.cache_data.clear()
            st.rerun()
    st.markdown(html, unsafe_allow_html=True)
    st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (지연 가능)")

render_ticker_line(build_ticker_items())

# =========================================
# 최신 뉴스
# =========================================
st.divider()
st.markdown("## 📰 최신 뉴스 요약")
c1,c2=st.columns([2,1])
with c1: cat=st.selectbox("📂 카테고리 선택", list(CATEGORIES))
with c2: page=st.number_input("페이지",min_value=1,value=1,step=1)

news_all = news_cache.get(cat, [])
page_size=10
news_page=news_all[(page-1)*page_size:page*page_size]
if not news_page:
    st.info("표시할 뉴스가 없습니다. (최근 3일 결과 없음)")
else:
    for i,n in enumerate(news_page, start=(page-1)*page_size+1):
        st.markdown(
            f"**{i}. [{n['title']}]({n['link']})**  \n"
            f"<span style='color:#9aa0a6;font-size:0.9rem'>{n['time']}</span><br>"
            f"<span style='color:#aeb8c5'>{n['desc']}</span>",
            unsafe_allow_html=True
        )
        st.markdown("<hr style='border:0;border-top:1px solid #1f2937'/>", unsafe_allow_html=True)
st.caption(f"최근 3일 · {cat} · 총 {len(news_all)}건")

# =========================================
# 테마 감지 (뉴스+가격 하이브리드) + 대표종목
# =========================================
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

# 통합 뉴스
all_news=[]
for lst in news_cache.values():
    all_news.extend(lst)

def detect_themes_hybrid(news_list, theme_kws:dict, price_boost=True, pct_threshold=2.0, min_stocks=2):
    # 뉴스 기반 카운트
    counts={t:0 for t in theme_kws}
    sample={t:"" for t in theme_kws}
    for n in news_list:
        text=(n["title"]+" "+n["desc"]).lower()
        for t,kws in theme_kws.items():
            if any(k in text for k in kws):
                counts[t]+=1
                if not sample[t]: sample[t]=n["link"]
    # 가격 기반
    price_info={}
    for theme, stocks in THEME_STOCKS.items():
        deltas=[]
        for _, tk in stocks:
            last, prev = fetch_quote(tk)
            if valid_prices(last, prev):
                deltas.append((last-prev)/prev*100.0)
        avg_delta = float(np.mean(deltas)) if deltas else 0.0
        up_cnt = sum(1 for d in deltas if d>0)
        price_info[theme]=(avg_delta, up_cnt)
        if price_boost and avg_delta>=pct_threshold and up_cnt>=min_stocks:
            counts[theme] = max(counts.get(theme,0), 1)  # 가격 주도로 최소 활성화
    # 결과
    rows=[]
    for theme in set(list(theme_kws.keys()) + list(THEME_STOCKS.keys())):
        c=counts.get(theme,0)
        avg_delta, up_cnt = price_info.get(theme,(0.0,0))
        if c>0 or (price_boost and avg_delta>=pct_threshold and up_cnt>=min_stocks):
            driver=("가격 주도" if (c==0 and avg_delta>=pct_threshold and up_cnt>=min_stocks)
                    else ("뉴스+가격" if (c>0 and avg_delta>=pct_threshold) else
                          ("뉴스 주도" if c>0 else "가격 주도")))
            rows.append({
                "theme": theme,
                "count": c,
                "avg_delta(%)": round(avg_delta,2),
                "up_cnt": int(up_cnt),
                "driver": driver,
                "sample_link": sample.get(theme,""),
                "rep_stocks": " · ".join([nm for nm,_ in THEME_STOCKS.get(theme,[])]) or "-"
            })
    rows.sort(key=lambda x:(x["count"], x["avg_delta(%)"]), reverse=True)
    return rows

theme_rows = detect_themes_hybrid(all_news, THEME_KEYWORDS, price_boost=True, pct_threshold=2.0, min_stocks=2)

if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다. (뉴스/가격 모두 약함)")
else:
    top5=theme_rows[:5]
    st.markdown(
        "**TOP 테마**: " + " ".join(
            [f"<span style='display:inline-block;border:1px solid #2b3a55;border-radius:10px;padding:6px 10px;margin:4px;background:#0f1420'><b>{r['theme']}</b> {r['count']}건 · {r['avg_delta(%)']}% · {r['driver']}</span>"
             for r in top5]),
        unsafe_allow_html=True
    )
    st.dataframe(pd.DataFrame(theme_rows), use_container_width=True, hide_index=True)

    st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")
    def safe_yf_price(tk):
        last, prev = fetch_quote(tk)
        if not valid_prices(last, prev): return None, None, "gray"
        delta=(last-prev)/prev*100
        color="red" if delta>0 else ("blue" if delta<0 else "gray")
        return fmt_number(last,0), fmt_percent(delta), color

    rng=np.random.default_rng(int(date.today().strftime("%Y%m%d")))
    for tr in top5:
        theme=tr["theme"]; pool=THEME_STOCKS.get(theme, [])
        if not pool: continue
        k=min(4, len(pool))
        picks=[pool[i] for i in rng.choice(len(pool), size=k, replace=False)]
        st.write(f"**{theme} — 주도: {tr['driver']} / 평균등락 {tr['avg_delta(%)']}%**")
        cols=st.columns(k)
        for col,(name,tk) in zip(cols, picks):
            with col:
                px,chg,color=safe_yf_price(tk)
                arrow="▲" if color=="red" else ("▼" if color=="blue" else "■")
                if px:
                    st.markdown(f"<b>{name}</b><br><span style='color:{color}'>{px} {arrow} {chg}</span><br><small>{tk}</small>", unsafe_allow_html=True)
                else:
                    st.markdown(f"**{name}**<br>-<br><small>{tk}</small>", unsafe_allow_html=True)
        st.divider()

# =========================================
# AI 뉴스 요약엔진 (더보기형)
# =========================================
st.divider()
st.markdown("## 🧠 AI 뉴스 요약엔진")
titles=[n["title"] for lst in news_cache.values() for n in lst[:60]]
words=[]
for t in titles:
    t=re.sub(r"[^가-힣A-Za-z0-9\s]"," ",t)
    words += [w for w in t.split() if len(w)>=2]
top_kw=[w for w,_ in Counter(words).most_common(10)]
st.markdown("### 📌 핵심 키워드 TOP10")
st.write(", ".join(top_kw) if top_kw else "-")

full_text=" ".join(titles)
sentences=re.split(r'[.!?]\s+', full_text)
summary=[s for s in sentences if len(s.strip())>20][:5]
st.markdown("### 📰 핵심 요약문")
if summary:
    st.markdown(f"**요약:** {summary[0][:150]}…")
    with st.expander("전체 요약문 보기 👇"):
        for s in summary: st.markdown(f"- {s.strip()}")
else:
    st.info("요약 데이터를 가져오지 못했습니다.")

# =====================================
# 테마별 상승 확률 리포트 (간단 스코어)
# =====================================
st.divider()
st.markdown("## 📊 AI 상승 확률 예측 리포트")

def calc_theme_strength(count, avg_delta):
    freq_score = min(count/20, 1.0)
    price_score = min(max((avg_delta+5)/10, 0), 1.0)
    return round((freq_score*0.6 + price_score*0.4) * 5, 1)

def calc_risk_level(avg_delta):
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

report_rows=[]
for tr in top5 if theme_rows else []:
    theme=tr["theme"]; stocks=THEME_STOCKS.get(theme, [])
    deltas=[]
    for _, tk in stocks:
        last, prev = fetch_quote(tk)
        if valid_prices(last, prev):
            deltas.append((last-prev)/prev*100)
    avg_delta=float(np.mean(deltas)) if deltas else 0.0
    report_rows.append({
        "테마": theme,
        "뉴스빈도": tr["count"],
        "평균등락(%)": round(avg_delta, 2),
        "테마강도(1~5)": calc_theme_strength(tr["count"], avg_delta),
        "리스크레벨(1~5)": calc_risk_level(avg_delta),
    })

if report_rows:
    st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)
else:
    st.info("리포트를 만들 데이터가 부족합니다.")

# =====================================
# 유망 종목 자동 추천 (Top5)
# =====================================
st.divider()
st.markdown("## 🚀 오늘의 AI 유망 종목 Top5")

def pick_promising_stocks(theme_rows, top_n=5):
    candidates=[]
    for tr in theme_rows[:8]:
        theme=tr["theme"]
        for name, tk in THEME_STOCKS.get(theme, []):
            last, prev = fetch_quote(tk)
            if not valid_prices(last, prev): 
                continue
            delta=(last-prev)/prev*100
            score = tr["count"]*0.3 + delta*0.7
            candidates.append({"테마":theme,"종목명":name,"등락률(%)":round(delta,2),
                               "뉴스빈도":tr["count"],"AI점수":round(score,2),"티커":tk})
    df=pd.DataFrame(candidates)
    return df.sort_values("AI점수", ascending=False).head(top_n) if not df.empty else df

recommend_df = pick_promising_stocks(theme_rows) if theme_rows else pd.DataFrame()

if recommend_df.empty:
    st.info("추천할 종목이 없습니다. 데이터가 부족하거나 시장 변동성이 낮습니다.")
else:
    st.dataframe(recommend_df, use_container_width=True, hide_index=True)
    st.markdown("### 🧾 AI 종합 판단")
    for _, row in recommend_df.iterrows():
        emoji="🔺" if row["등락률(%)"]>0 else "🔻"
        st.markdown(
            f"**{emoji} {row['종목명']} ({row['티커']})** — "
            f"테마: *{row['테마']}*, 최근 등락률: **{row['등락률(%)']}%**, "
            f"뉴스빈도: {row['뉴스빈도']}건, AI점수: {row['AI점수']}"
        )

st.caption("※ AI점수 = 뉴스활성도 + 주가상승률 기반 유망도 산출")

# =====================================
# 3일 예측(로지스틱)
# =====================================
st.divider()
st.markdown("## 🔮 AI 3일 예측: 내일 오를 확률")

@st.cache_data(ttl=600)
def load_hist(ticker: str, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    return df[~df.index.duplicated(keep='last')].dropna()

def rsi(series: pd.Series, period: int = 14):
    delta = series.diff()
    up = np.where(delta>0, delta, 0.0)
    down = np.where(delta<0, -delta, 0.0)
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
    return macd_line, signal_line, macd_line - signal_line

def build_features(df: pd.DataFrame):
    price = df["Close"]
    feat = pd.DataFrame(index=df.index)
    feat["ret_1d"] = price.pct_change(1)
    feat["ret_5d"] = price.pct_change(5)
    feat["ret_10d"] = price.pct_change(10)
    feat["vol_5d"] = price.pct_change().rolling(5).std()
    feat["vol_20d"] = price.pct_change().rolling(20).std()
    feat["rsi_14"] = rsi(price, 14)
    macd_line, sig, hist = macd(price)
    feat["macd"] = macd_line; feat["macd_sig"] = sig; feat["macd_hist"] = hist
    ma5=price.rolling(5).mean(); ma20=price.rolling(20).mean()
    feat["ma5_gap"] = (price-ma5)/ma5; feat["ma20_gap"] = (price-ma20)/ma20
    y = (price.shift(-1) > price).astype(int)
    return pd.concat([feat, y.rename("y")], axis=1).dropna()

def fit_predict_prob(df_feat: pd.DataFrame):
    if len(df_feat) < 120:
        return None, None
    data = df_feat.tail(300)
    X = data.drop(columns=["y"]).values
    y = data["y"].values
    n = len(data); split = max(60, n-3)
    X_train, y_train, X_pred = X[:split], y[:split], X[split:]
    model = LogisticRegression(max_iter=200)
    model.fit(X_train, y_train)
    prob = model.predict_proba(X_pred)[:,1]
    p_tomorrow = float(prob[0]) if len(prob)>0 else None
    p_3avg = float(prob.mean()) if len(prob)>0 else None
    return p_tomorrow, p_3avg

rows=[]
if recommend_df.empty:
    st.info("먼저 '유망 종목 Top5'가 생성되어야 예측을 수행합니다.")
else:
    with st.spinner("예측 계산 중..."):
        for _, r in recommend_df.iterrows():
            name, tk = r["종목명"], r["티커"]
            try:
                hist = load_hist(tk)
                if hist.empty:
                    rows.append({"종목명":name,"티커":tk,"내일상승확률":"-","3일평균확률":"-","신호":"데이터부족"})
                    continue
                feats = build_features(hist)
                p1, p3 = fit_predict_prob(feats)
                if p1 is None:
                    rows.append({"종목명":name,"티커":tk,"내일상승확률":"-","3일평균확률":"-","신호":"데이터부족"})
                else:
                    signal = "매수관심" if p1>=0.55 else ("관망" if p1>=0.45 else "주의")
                    rows.append({"종목명":name,"티커":tk,"내일상승확률":round(p1*100,1),
                                 "3일평균확률":round(p3*100,1),"신호":signal})
            except Exception:
                rows.append({"종목명":name,"티커":tk,"내일상승확률":"-","3일평균확률":"-","신호":"오류"})

pred_df = pd.DataFrame(rows)
if not pred_df.empty:
    def _prob_color(v):
        try: v=float(v)
        except: return ""
        if v>=60: return "background-color: rgba(217,48,37,0.18); color:#ffd2cf; font-weight:700;"
        if v>=50: return "background-color: rgba(255,193,7,0.12);"
        return "background-color: rgba(26,115,232,0.14); color:#d7e6ff;"
    st.dataframe(pred_df.style.map(_prob_color, subset=["내일상승확률","3일평균확률"]),
                 use_container_width=True, hide_index=True)
    st.markdown("### 🧠 AI 인사이트")
    for _, row in pred_df.iterrows():
        if row["내일상승확률"] == "-":
            st.markdown(f"- **{row['종목명']} ({row['티커']})** — 데이터 부족/오류")
        else:
            arrow = "🔺" if row["내일상승확률"] >= 50 else "🔻"
            st.markdown(
                f"- **{row['종목명']} ({row['티커']})** — 내일 상승 확률 **{row['내일상승확률']}%** "
                f"(3일 평균 {row['3일평균확률']}%), 신호: **{row['신호']}** {arrow}"
            )

st.caption("※ 간단한 로지스틱 회귀 기반 참고지표입니다. 투자 판단의 책임은 본인에게 있습니다.")

# =========================================
# 테마 관리자 (저장 UI)
# =========================================
st.divider()
st.markdown("## 🛠 테마 관리자")

theme_cfg: dict = st.session_state.theme_cfg
left, right = st.columns([1,2])

with left:
    st.markdown("**테마 선택/추가**")
    names = sorted(theme_cfg.keys())
    selected = st.selectbox("테마", options=["(새로 만들기)"] + names, index=0)
    new_name = st.text_input("테마 이름", value="" if selected=="(새로 만들기)" else selected)

with right:
    st.markdown("**키워드 & 종목 편집**")
    cur = theme_cfg.get(selected, {"keywords":[], "stocks":[]}) if selected!="(새로 만들기)" else {"keywords":[], "stocks":[]}
    kw_text = st.text_area("키워드 (쉼표로 구분)", value=", ".join(cur.get("keywords", [])),
                           placeholder="예) 전력, 송전, HVDC, 전력망 …")
    stock_text = st.text_area(
        "종목 목록 (한 줄에 `종목명,티커`)",
        value="\n".join([f"{s['name']},{s['ticker']}" for s in cur.get("stocks", [])]),
        placeholder="예)\n한국전력,015760.KS\n한전KPS,051600.KS"
    )

    c1,c2,c3 = st.columns(3)
    with c1:
        if st.button("💾 저장/업데이트"):
            if not new_name.strip():
                st.error("테마 이름을 입력하세요.")
            else:
                kws = [k.strip() for k in kw_text.split(",") if k.strip()]
                stocks=[]
                for line in stock_text.splitlines():
                    line=line.strip()
                    if not line: continue
                    if "," not in line:
                        st.warning(f"잘못된 종목 입력: `{line}` (콤마로 구분 필요)")
                        continue
                    nm, tk = [x.strip() for x in line.split(",",1)]
                    stocks.append({"name":nm, "ticker":tk})
                theme_cfg[new_name.strip()] = {"keywords":kws, "stocks":stocks}
                save_theme_config(theme_cfg)
                pushed = push_to_github_file(theme_cfg)
                st.success("저장 완료! " + ("(로컬+GitHub)" if pushed else "(로컬 저장)"))
                st.session_state.theme_cfg = theme_cfg
                st.rerun()
    with c2:
        if st.button("🗑 삭제"):
            if selected=="(새로 만들기)":
                st.warning("삭제할 기존 테마를 선택하세요.")
            else:
                theme_cfg.pop(selected, None)
                save_theme_config(theme_cfg)
                push_to_github_file(theme_cfg)
                st.success("테마 삭제 완료.")
                st.session_state.theme_cfg = theme_cfg
                st.rerun()
    with c3:
        st.download_button(
            "⬇ themes.json 다운로드",
            data=json.dumps(theme_cfg, ensure_ascii=False, indent=2),
            file_name="themes.json",
            mime="application/json",
        )

st.caption("💡 영구 저장을 원하면 Secrets에 `GITHUB_TOKEN`, `THEME_REPO`, `THEME_PATH` 설정.")
