# -*- coding: utf-8 -*-
"""
AI 뉴스리포트 – 컴팩트 뉴스/슬림 퀵메뉴 반영 버전
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

# =========================
# 페이지/글로벌 스타일
# =========================
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")

GLOBAL_CSS = """
<style>
/* 본문 가독성 */
.block-container { padding-top: 1.0rem; padding-bottom: 2.4rem; }
h2, h3 { letter-spacing: -0.3px; }

/* 링크 톤 */
a, a:visited { color: #7aa2ff; text-decoration: none; }
a:hover { text-decoration: underline; }

/* 우측 퀵메뉴 바 (슬림) */
.quick-nav {
  position: fixed; right: 12px; top: 92px; z-index: 9999;
  width: 176px; max-height: 74vh; overflow:auto;
  background:#0f1420; border:1px solid #2b3a55; border-radius: 10px;
  padding: 8px 8px; box-shadow: 0 6px 18px rgba(0,0,0,0.24);
}
.quick-nav h4 { margin: 4px 6px 6px; font-size: 0.88rem; color:#cbd5e1 }
.quick-nav a {
  display:block; padding:6px 8px; margin:4px 6px;
  font-size:0.85rem; color:#9fb3c8; border-radius:8px; border:1px solid #223050;
  background:#0b1220;
}
.quick-nav a:hover { background:#0f1a2c; border-color:#2a3b5e; color:#cfe3ff }

/* 티커바 */
.ticker-wrap{overflow:hidden;width:100%;border:1px solid #263042;border-radius:10px;background:#0f1420}
.ticker-track{display:flex;gap:16px;align-items:center;width:max-content;will-change:transform;animation:ticker-scroll var(--speed,28s) linear infinite}
@keyframes ticker-scroll{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
.badge{display:inline-flex;align-items:center;gap:8px;background:#0f1420;border:1px solid #2b3a55;color:#c7d2fe;padding:6px 10px;border-radius:8px;font-weight:700;white-space:nowrap}
.badge .name{color:#9fb3c8;font-weight:600}
.badge .up{color:#d93025}.badge .down{color:#1a73e8}.sep{color:#44526b;padding:0 6px}

/* 대표 종목 카드 */
.card-grid { display:grid; gap:12px; grid-template-columns: repeat(auto-fit, minmax(170px,1fr)); }
.stock-card {
  border:1px solid #22324a; background:#0f1420; border-radius:12px; padding:10px 12px;
  transition: transform .08s ease, border-color .08s ease, background .08s ease;
}
.stock-card:hover { transform: translateY(-2px); border-color:#2d456a; background:#111a2a; }
.stock-card .nm { font-weight:700; }
.stock-card .ticker { color:#90a4bf; font-size:0.8rem;}
.stock-card .px { font-size:1.02rem; margin-top:4px; }
.stock-card .up { color:#d93025 }   /* 빨강 */
.stock-card .down { color:#1a73e8 } /* 파랑 */
.stock-card .flat { color:#9aa0a6 }

/* 요약 가독성 */
.readable p, .readable li { line-height: 1.52; color:#cdd6e4; }
.readable ul { margin:0 0 0.2rem 0.9rem; }

/* 작은 캡션 */
.small-cap { color:#9aa0a6; font-size:0.86rem; }

/* 뉴스 컴팩트 리스트 */
.news-compact { margin-top: .2rem; }
.news-compact .item { padding: 3px 0 1px 0; margin: 0; }
.news-compact .ttl  { font-weight: 700; }
.news-compact .dt   { color:#9aa0a6; font-size:.84rem; }
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)
st.markdown(f"<small class='small-cap'>업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}</small>", unsafe_allow_html=True)

# =========================
# 유틸
# =========================
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
    if last is None or prev in (None, 0):
        return False
    try:
        if isinstance(last, float) and (math.isnan(last) or math.isinf(last)): return False
        if isinstance(prev, float) and (math.isnan(prev) or math.isinf(prev)): return False
    except Exception:
        pass
    return True

# =========================
# 테마 설정 저장/로드
# =========================
THEME_STORE_PATH = Path("themes.json")
DEFAULT_THEME_CFG = {
    "AI": {"keywords": ["ai","인공지능","생성형","챗봇","엔비디아","오픈ai","gpu"],
           "stocks": [{"name":"삼성전자","ticker":"005930.KS"},
                      {"name":"네이버","ticker":"035420.KS"},
                      {"name":"카카오","ticker":"035720.KS"}]},
    "반도체":{"keywords":["반도체","hbm","메모리","파운드리","칩","램","소부장"],
           "stocks":[{"name":"SK하이닉스","ticker":"000660.KS"},
                     {"name":"DB하이텍","ticker":"000990.KS"},
                     {"name":"리노공업","ticker":"058470.KQ"}]},
    "전력":{"keywords":["전력","송전","배전","송배전","전력망","hvdc","한국전력","한전kps","한전기술","전선","케이블"],
           "stocks":[{"name":"한국전력","ticker":"015760.KS"},
                     {"name":"한전KPS","ticker":"051600.KS"},
                     {"name":"한전기술","ticker":"052690.KS"},
                     {"name":"대한전선","ticker":"001440.KS"},
                     {"name":"LS ELECTRIC","ticker":"010120.KS"}]},
    "에너지":{"keywords":["에너지","정유","전력","태양광","풍력","가스"],
           "stocks":[{"name":"두산에너빌리티","ticker":"034020.KS"},
                     {"name":"한화솔루션","ticker":"009830.KS"},
                     {"name":"GS","ticker":"078930.KS"}]},
    "조선":{"keywords":["조선","선박","lng선","해운"],
           "stocks":[{"name":"HD한국조선해양","ticker":"009540.KS"},
                     {"name":"HD현대미포","ticker":"010620.KS"},
                     {"name":"한화오션","ticker":"042660.KS"},
                     {"name":"삼성중공업","ticker":"010140.KS"}]},
    "원전":{"keywords":["원전","smr","원자력","우라늄"],
           "stocks":[{"name":"두산에너빌리티","ticker":"034020.KS"},
                     {"name":"우진","ticker":"105840.KQ"},
                     {"name":"한전KPS","ticker":"051600.KS"},
                     {"name":"보성파워텍","ticker":"006910.KQ"}]},
    "이차전지":{"keywords":["배터리","이차전지","전고체","양극재","음극재","lfp"],
           "stocks":[{"name":"LG에너지솔루션","ticker":"373220.KS"},
                     {"name":"포스코퓨처엠","ticker":"003670.KS"},
                     {"name":"에코프로","ticker":"086520.KQ"}]},
    "바이오":{"keywords":["바이오","제약","신약","임상"],
           "stocks":[{"name":"셀트리온","ticker":"068270.KS"},
                     {"name":"에스티팜","ticker":"237690.KQ"},
                     {"name":"알테오젠","ticker":"196170.KQ"},
                     {"name":"메디톡스","ticker":"086900.KQ"}]},
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
    try:
        token = st.secrets.get("GITHUB_TOKEN"); repo  = st.secrets.get("THEME_REPO")
        path  = st.secrets.get("THEME_PATH", "themes.json")
        if not token or not repo: return False
        import requests
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

# =========================
# 시세/뉴스
# =========================
def fetch_quote(ticker: str):
    try:
        t = yf.Ticker(ticker)
        last, prev = getattr(t.fast_info, "last_price", None), getattr(t.fast_info, "previous_close", None)
        if valid_prices(last, prev): return float(last), float(prev)
    except Exception: pass
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        c = df.get("Close")
        if c is None or c.dropna().empty: return None, None
        c = c.dropna()
        last, prev = float(c.iloc[-1]), (float(c.iloc[-2]) if len(c) >= 2 else None)
        return (last, prev) if valid_prices(last, prev) else (None, None)
    except Exception:
        return None, None

def clean_html(raw):
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days):
    now = datetime.now(KST); out = []
    for e in feed.entries:
        t = None
        if getattr(e, "published_parsed", None): t = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None): t = datetime(*e.updated_parsed[:6], tzinfo=KST)
        if t and (now - t) > timedelta(days=days): continue
        title, link = e.get("title","").strip(), e.get("link","").strip()
        if link.startswith("./"): link = "https://news.google.com/" + link[2:]
        desc = clean_html(e.get("summary",""))
        out.append({"title":title, "link":link, "time":t.strftime("%Y-%m-%d %H:%M") if t else "-", "desc":desc})
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

@st.cache_data(ttl=600, show_spinner=False)
def fetch_category_news(cat, days=3, max_items=100):
    seen, out = set(), []
    for kw in CATEGORIES.get(cat, []):
        try:
            for it in fetch_google_news_by_keyword(kw, days):
                k = (it["title"], it["link"])
                if k in seen: continue
                seen.add(k); out.append(it)
        except Exception: continue
    def key(x):
        try: return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except: return datetime.min
    return sorted(out, key=key, reverse=True)[:max_items]

@st.cache_data(ttl=600, show_spinner=False)
def load_all_news_3days() -> dict:
    return {c: fetch_category_news(c, 3, 100) for c in CATEGORIES.keys()}

news_cache = load_all_news_3days()

# =========================
# 우측 고정 퀵 메뉴
# =========================
QUICK_MENU_HTML = """
<div class="quick-nav">
  <h4>Quick Menu</h4>
  <a href="#sec-ticker">📊 시장 요약</a>
  <a href="#sec-latest-news">📰 최신 뉴스</a>
  <a href="#sec-theme">🔥 테마 요약</a>
  <a href="#sec-ai-sum">🧠 뉴스 요약엔진</a>
  <a href="#sec-theme-score">📈 상승 확률</a>
  <a href="#sec-top5">🚀 유망 Top5</a>
  <a href="#sec-predict">🔮 3일 예측</a>
  <a href="#sec-admin">🛠 테마 관리</a>
</div>
"""
st.markdown(QUICK_MENU_HTML, unsafe_allow_html=True)

# =========================
# 1) 티커바
# =========================
st.markdown('<div id="sec-ticker"></div>', unsafe_allow_html=True)

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
            d = last - prev; p = (d / prev) * 100
        items.append({"name":name,"last":fmt_number(last, dp),
                      "pct": fmt_percent(p) if p is not None else "--",
                      "is_up":(d or 0)>0,"is_down":(d or 0)<0})
    return items

def render_ticker_line(items, speed_sec=28):
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
        if st.button("🔄 새로고침", key="btn_refresh_ticker"):
            st.cache_data.clear(); st.rerun()
    st.markdown(html, unsafe_allow_html=True)
    st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (지연 가능)")

render_ticker_line(build_ticker_items())

# =========================
# 2) 최신 뉴스 (컴팩트: 제목 + 날짜/시간)
# =========================
st.markdown('<div id="sec-latest-news"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 📰 최신 뉴스")

cat_options = list(CATEGORIES.keys())
if "cur_cat" not in st.session_state:
    st.session_state.cur_cat = cat_options[0]

c1, c2 = st.columns([2, 1])
with c1:
    cur_cat = st.selectbox("📂 카테고리 선택", options=cat_options,
                           index=cat_options.index(st.session_state.cur_cat), key="sel_cat_compact")
    st.session_state.cur_cat = cur_cat
with c2:
    page = st.number_input("페이지", min_value=1, value=1, step=1, key="news_page_compact")

news_all = news_cache.get(st.session_state.cur_cat, [])
page_size = 10
start, end = (page-1)*page_size, page*page_size
news_page = news_all[start:end]

if not news_page:
    st.info("표시할 뉴스가 없습니다. (최근 3일 결과 없음)")
else:
    st.markdown("<div class='news-compact'>", unsafe_allow_html=True)
    for i, n in enumerate(news_page, start=start+1):
        title = n.get("title","-"); link  = n.get("link",""); when  = n.get("time","-")
        st.markdown(
            f"<div class='item'><a class='ttl' href='{link}' target='_blank'>{i}. {title}</a><br>"
            f"<span class='dt'>{when}</span></div>", unsafe_allow_html=True
        )
    st.markdown("</div>", unsafe_allow_html=True)

st.caption(f"최근 3일 · {st.session_state.cur_cat} · 총 {len(news_all)}건 중 {start+1}–{min(end, len(news_all))} 표시")

# =========================
# 3) 테마 감지(뉴스+가격) + 링크/대표종목
# =========================
st.markdown('<div id="sec-theme"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

def detect_themes_hybrid(news_list, theme_kws:dict, price_boost=True, pct_threshold=2.0, min_stocks=2):
    counts={t:0 for t in theme_kws}
    sample={t:"" for t in theme_kws}
    for n in news_list:
        text=(n["title"]+" "+n["desc"]).lower()
        for t,kws in theme_kws.items():
            if any(k in text for k in kws):
                counts[t]+=1
                if not sample[t]: sample[t]=n["link"]
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
            counts[theme] = max(counts.get(theme,0), 1)
    rows=[]
    for theme in set(list(theme_kws.keys()) + list(THEME_STOCKS.keys())):
        c=counts.get(theme,0)
        avg_delta, up_cnt = price_info.get(theme,(0.0,0))
        if c>0 or (price_boost and avg_delta>=pct_threshold and up_cnt>=min_stocks):
            driver=("가격 주도" if (c==0 and avg_delta>=pct_threshold and up_cnt>=min_stocks)
                    else ("뉴스+가격" if (c>0 and avg_delta>=pct_threshold) else
                          ("뉴스 주도" if c>0 else "가격 주도")))
            rows.append({
                "테마": theme,
                "뉴스건수": c,
                "평균등락(%)": round(avg_delta,2),
                "상승종목수": int(up_cnt),
                "주도요인": driver,
                "샘플링크": sample.get(theme,""),
                "대표종목": " · ".join([nm for nm,_ in THEME_STOCKS.get(theme,[])]) or "-"
            })
    rows.sort(key=lambda x:(x["뉴스건수"], x["평균등락(%)"]), reverse=True)
    return rows

all_news=[]; [all_news.extend(v) for v in news_cache.values()]
theme_rows = detect_themes_hybrid(all_news, THEME_KEYWORDS, True, 2.0, 2)

if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다. (뉴스/가격 모두 약함)")
else:
    df_theme = pd.DataFrame(theme_rows)
    df_theme["링크"] = df_theme["샘플링크"].apply(lambda u: u if isinstance(u,str) and u else "")
    try:
        st.dataframe(
            df_theme.drop(columns=["샘플링크"]),
            use_container_width=True, hide_index=True,
            column_config={"링크": st.column_config.LinkColumn("샘플 뉴스", display_text="열기")}
        )
    except Exception:
        st.dataframe(df_theme.drop(columns=["샘플링크"]), use_container_width=True, hide_index=True)
        st.caption("※ 샘플 뉴스 링크는 표의 '링크' 칼럼 URL을 클릭하세요.")

    st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")
    def rep_price(tk):
        last, prev = fetch_quote(tk)
        if not valid_prices(last, prev): return None, None, "flat"
        delta=(last-prev)/prev*100
        tone = "up" if delta>0 else ("down" if delta<0 else "flat")
        return fmt_number(last,0), fmt_percent(delta), tone

    top5 = df_theme.head(5).to_dict("records")
    for tr in top5:
        theme = tr["테마"]; stocks = THEME_STOCKS.get(theme, [])[:6]
        if not stocks: continue
        st.markdown(f"**{theme}** — <span class='small-cap'>주도: {tr['주도요인']} · 평균등락 {tr['평균등락(%)']}%</span>", unsafe_allow_html=True)
        cards = []
        for nm, tk in stocks:
            px, chg, tone = rep_price(tk)
            arrow = "▲" if tone=="up" else ("▼" if tone=="down" else "■")
            if px is None:
                html = f"<div class='stock-card'><div class='nm'>{nm}</div><div class='ticker'>{tk}</div><div class='px flat'>-</div></div>"
            else:
                html = f"<div class='stock-card'><div class='nm'>{nm}</div><div class='ticker'>{tk}</div><div class='px {tone}'>{px} {arrow} {chg}</div></div>"
            cards.append(html)
        st.markdown(f"<div class='card-grid'>{''.join(cards)}</div>", unsafe_allow_html=True)

# =========================
# 4) AI 뉴스 요약엔진 (가독성 업)
# =========================
st.markdown('<div id="sec-ai-sum"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🧠 AI 뉴스 요약엔진")

titles=[n["title"] for lst in news_cache.values() for n in lst[:60]]
words=[]
for t in titles:
    t=re.sub(r"[^가-힣A-Za-z0-9\s]"," ",t); words += [w for w in t.split() if len(w)>=2]
top_kw=[w for w,_ in Counter(words).most_common(10)]

st.markdown("### 📌 핵심 키워드 TOP10")
st.write(", ".join(top_kw) if top_kw else "-")

full_text=" ".join(titles)
sentences=re.split(r'[.!?]\s+', full_text)
summary=[s for s in sentences if len(s.strip())>20][:5]

st.markdown("### 📰 핵심 요약문")
if summary:
    st.markdown(f"**요약:** {summary[0][:160]}…")
    with st.expander("전체 요약문 보기 👇"):
        st.markdown("<div class='readable'>", unsafe_allow_html=True)
        st.markdown("\n".join([f"- {s.strip()}" for s in summary]))
        st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("요약 데이터를 가져오지 못했습니다.")

# =========================
# 5) 테마별 상승 확률 리포트
# =========================
st.markdown('<div id="sec-theme-score"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 📈 AI 상승 확률 예측 리포트")

def calc_theme_strength(count, avg_delta):
    freq_score = min(count/20, 1.0); price_score = min(max((avg_delta+5)/10, 0), 1.0)
    return round((freq_score*0.6 + price_score*0.4) * 5, 1)
def calc_risk_level(avg_delta):
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

report_rows=[]
if theme_rows:
    for tr in theme_rows[:5]:
        theme=tr["테마"]; stocks=THEME_STOCKS.get(theme, [])
        deltas=[]
        for _, tk in stocks:
            last, prev = fetch_quote(tk)
            if valid_prices(last, prev): deltas.append((last-prev)/prev*100)
        avg_delta=float(np.mean(deltas)) if deltas else 0.0
        report_rows.append({
            "테마": theme,
            "뉴스빈도": tr["뉴스건수"],
            "평균등락(%)": round(avg_delta, 2),
            "테마강도(1~5)": calc_theme_strength(tr["뉴스건수"], avg_delta),
            "리스크레벨(1~5)": calc_risk_level(avg_delta),
        })

if report_rows:
    st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)
else:
    st.info("리포트를 만들 데이터가 부족합니다.")

# =========================
# 6) 유망 종목 Top5
# =========================
st.markdown('<div id="sec-top5"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🚀 오늘의 AI 유망 종목 Top5")

def pick_promising_stocks(theme_rows, top_n=5):
    candidates=[]
    for tr in theme_rows[:8]:
        theme=tr["테마"]
        for name, tk in THEME_STOCKS.get(theme, []):
            last, prev = fetch_quote(tk)
            if not valid_prices(last, prev): continue
            delta=(last-prev)/prev*100
            score = tr["뉴스건수"]*0.3 + delta*0.7
            candidates.append({"테마":theme,"종목명":name,"등락률(%)":round(delta,2),
                               "뉴스빈도":tr["뉴스건수"],"AI점수":round(score,2),"티커":tk})
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
            f"- **{emoji} {row['종목명']} ({row['티커']})** — "
            f"테마: *{row['테마']}*, 최근 등락률: **{row['등락률(%)']}%**, "
            f"뉴스빈도: {row['뉴스빈도']}건, AI점수: {row['AI점수']}"
        )

# =========================
# 7) 3일 예측(로지스틱)
# =========================
st.markdown('<div id="sec-predict"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🔮 AI 3일 예측: 내일 오를 확률")

@st.cache_data(ttl=600)
def load_hist(ticker: str, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    return df[~df.index.duplicated(keep='last')].dropna()
def rsi(series: pd.Series, period: int = 14):
    delta = series.diff(); up = np.where(delta>0, delta, 0.0); down = np.where(delta<0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    return (100 - (100 / (1 + rs))).fillna(50)
def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow; signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line
def build_features(df: pd.DataFrame):
    price = df["Close"]; feat = pd.DataFrame(index=df.index)
    feat["ret_1d"] = price.pct_change(1);  feat["ret_5d"] = price.pct_change(5);  feat["ret_10d"] = price.pct_change(10)
    feat["vol_5d"] = price.pct_change().rolling(5).std(); feat["vol_20d"] = price.pct_change().rolling(20).std()
    feat["rsi_14"] = rsi(price, 14); macd_line, sig, hist = macd(price)
    feat["macd"] = macd_line; feat["macd_sig"] = sig; feat["macd_hist"] = hist
    ma5=price.rolling(5).mean(); ma20=price.rolling(20).mean()
    feat["ma5_gap"] = (price-ma5)/ma5; feat["ma20_gap"] = (price-ma20)/ma20
    y = (price.shift(-1) > price).astype(int)
    return pd.concat([feat, y.rename("y")], axis=1).dropna()
def fit_predict_prob(df_feat: pd.DataFrame):
    if len(df_feat) < 120: return None, None
    data = df_feat.tail(300); X = data.drop(columns=["y"]).values; y = data["y"].values
    n = len(data); split = max(60, n-3); X_train, y_train, X_pred = X[:split], y[:split], X[split:]
    model = LogisticRegression(max_iter=200); model.fit(X_train, y_train)
    prob = model.predict_proba(X_pred)[:,1]
    return (float(prob[0]) if len(prob)>0 else None, float(prob.mean()) if len(prob)>0 else None)

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
                feats = build_features(hist); p1, p3 = fit_predict_prob(feats)
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

# =========================
# 8) 테마 관리자 (저장 UI)
# =========================
st.markdown('<div id="sec-admin"></div>', unsafe_allow_html=True)
st.divider(); st.markdown("## 🛠 테마 관리자")

theme_cfg: dict = st.session_state.theme_cfg
left, right = st.columns([1,2])
with left:
    st.markdown("**테마 선택/추가**")
    names = sorted(theme_cfg.keys())
    if "admin_selected" not in st.session_state:
        st.session_state.admin_selected = "(새로 만들기)"
    select_options = ["(새로 만들기)"] + names
    try:
        default_idx = select_options.index(st.session_state.admin_selected)
    except ValueError:
        default_idx = 0
    selected = st.selectbox("테마", options=select_options, index=default_idx, key="admin_sel")
    st.session_state.admin_selected = selected
    new_name = st.text_input("테마 이름", value="" if selected=="(새로 만들기)" else selected)
with right:
    st.markdown("**키워드 & 종목 편집**")
    cur = theme_cfg.get(selected, {"keywords":[], "stocks":[]}) if selected!="(새로 만들기)" else {"keywords":[], "stocks":[]}
    kw_text = st.text_area("키워드 (쉼표로 구분)", value=", ".join(cur.get("keywords", [])),
                           placeholder="예) 전력, 송전, HVDC, 전력망 …", key="admin_kw")
    stock_text = st.text_area(
        "종목 목록 (한 줄에 `종목명,티커`)",
        value="\n".join([f"{s['name']},{s['ticker']}" for s in cur.get("stocks", [])]),
        placeholder="예)\n한국전력,015760.KS\n한전KPS,051600.KS",
        key="admin_stocks"
    )
    c1,c2,c3 = st.columns(3)
    with c1:
        if st.button("💾 저장/업데이트", key="btn_admin_save"):
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
        if st.button("🗑 삭제", key="btn_admin_del"):
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
