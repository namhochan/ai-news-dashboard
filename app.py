# app.py
import os, json, re
from datetime import datetime
import pandas as pd
import streamlit as st

# =======================
# 기본 설정
# =======================
DATA_DIR = "data"
st.set_page_config(page_title="AI 뉴스리포트 대시보드", layout="wide")
st.title("🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")

# =======================
# JSON 로드 유틸
# =======================
def load_json(name, default=None):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except:
        return default

market = load_json("market_today.json", {})
headlines = load_json("headlines_top10.json", [])
themes_top = load_json("theme_top5.json", [])
themes_sub = load_json("theme_secondary5.json", [])
prices = load_json("stock_prices.json", {})
theme_map = load_json("theme_stock_map.json", {})
news100 = load_json("news_100.json", [])

# =======================
# 1️⃣ 시장 지수 / 원자재 / 환율
# =======================
st.header("📊 오늘의 시장 요약")

col1, col2, col3 = st.columns(3)
def show_metric(col, name, key):
    item = market.get(key, {})
    price = item.get("price")
    change = item.get("change_pct")
    val = f"{price:,.2f}" if price else "-"
    delta = f"{change:+.2f}%" if change else "-"
    col.metric(name, val, delta)

show_metric(col1, "KOSPI", "KOSPI")
show_metric(col2, "KOSDAQ", "KOSDAQ")
show_metric(col3, "환율(USD/KRW)", "USD/KRW")

col4, col5, col6 = st.columns(3)
show_metric(col4, "WTI", "WTI")
show_metric(col5, "Gold", "Gold")
show_metric(col6, "Copper", "Copper")

st.caption(f"업데이트 시간: {market.get('_updated_at', '-')}")
st.divider()

# =======================
# 2️⃣ 상단 Top10 뉴스
# =======================
st.header("📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")

if not headlines:
    st.info("뉴스 데이터 없음")
else:
    for n in headlines:
        st.markdown(f"**[{n['title']}]({n['link']})**")
        st.caption(f"🕒 {n.get('published','')}  |  🔍 검색어: {n.get('query','')}")
st.divider()

# =======================
# 3️⃣ 메인 테마 TOP 5
# =======================
st.header("🔥 메인 테마 TOP 5")

if themes_top:
    df_top = pd.DataFrame(themes_top)
    st.bar_chart(df_top.set_index("theme")["count"])
    for t in themes_top:
        st.subheader(f"🏷️ {t['theme']} (언급 {t['count']}회)")
        st.caption(f"[관련 뉴스 보기]({t['sample_link']})")
else:
    st.info("테마 데이터 없음")
st.divider()

# =======================
# 4️⃣ 보조 테마 5
# =======================
st.header("🧩 보조 테마 5")

if themes_sub:
    df_sub = pd.DataFrame(themes_sub)
    st.bar_chart(df_sub.set_index("theme")["count"])
    for t in themes_sub:
        st.markdown(f"- [{t['theme']}]({t['sample_link']}) ({t['count']}회)")
else:
    st.info("보조 테마 없음")
st.divider()

# =======================
# 5️⃣ 테마별 대표 종목 & 주가/뉴스
# =======================
st.header("💹 테마별 대표 종목 및 최신 뉴스")

def show_stock_block(name, ticker):
    key = ticker if ticker and ticker != "—" else name
    file_path = os.path.join(DATA_DIR, "stock_news", f"{key}.json")
    if not os.path.exists(file_path):
        st.caption(f"{name}: 뉴스 데이터 없음")
        return

    data = json.load(open(file_path, "r", encoding="utf-8"))
    st.subheader(f"{name} ({ticker if ticker and ticker!='—' else '티커없음'})")

    if ticker in prices:
        p = prices[ticker]
        price = p.get("price")
        change = p.get("change_pct")
        val = f"{price:,.2f}" if price else "-"
        delta = f"{change:+.2f}%" if change else "-"
        st.metric("현재가", val, delta)

    for n in data.get("news", [])[:5]:
        st.markdown(f"- [{n['title']}]({n['link']}) ({n.get('published','')})")

def show_theme(theme_name):
    stocks = theme_map.get(theme_name, {}).get("stocks", [])[:5]
    if not stocks:
        st.write("종목 매핑 없음")
        return
    cols = st.columns(min(5, len(stocks)))
    for i, (name, ticker) in enumerate(stocks):
        with cols[i % len(cols)]:
            show_stock_block(name, ticker)

# 메인 테마
if themes_top:
    for t in themes_top:
        st.subheader(f"🔥 {t['theme']} 관련 종목")
        show_theme(t["theme"])
st.divider()

# 보조 테마
if themes_sub:
    st.header("🧭 보조 테마 관련 종목")
    for t in themes_sub:
        with st.expander(f"{t['theme']}"):
            show_theme(t["theme"])

# =======================
# 6️⃣ 뉴스 키워드 요약 (100개 뉴스 기준)
# =======================
st.header("🔍 뉴스 키워드 상위 빈도 Top 30")

if news100:
    tokens = []
    for n in news100:
        parts = re.findall(r"[가-힣A-Za-z0-9]{2,}", n["title"])
        tokens.extend(parts)
    df_words = pd.Series(tokens).value_counts().head(30).sort_values(ascending=True)
    st.bar_chart(df_words)
else:
    st.info("뉴스 키워드 없음")

st.markdown("---")
st.caption("ⓒ 자동 크롤링 기반 AI 뉴스리포트 대시보드 · Google News RSS + yfinance · 1시간 단위 자동 업데이트")
