# app.py
import json, os
from datetime import datetime
import pytz
import streamlit as st
import plotly.express as px

DATA_DIR = "data"
MARKET_PATH   = os.path.join(DATA_DIR, "market_today.json")
THEME_PATH    = os.path.join(DATA_DIR, "theme_top5.json")
KEYWORD_PATH  = os.path.join(DATA_DIR, "keyword_map.json")
KST = pytz.timezone("Asia/Seoul")

st.set_page_config(page_title="AI 뉴스리포트 V27.0 – Web Dashboard Edition", layout="wide")

def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}

# 헤더
st.title("📊 AI 뉴스리포트 V27.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")

# 데이터 로드
market = load_json(MARKET_PATH, {})
themes = load_json(THEME_PATH, {})
kmap   = load_json(KEYWORD_PATH, {})

st.caption(f"🕒 지표/환율 갱신: {market.get('updated_at_kst','-')} (KST)")

# =============== 오늘의 시장 요약 ===============
st.subheader("📉 오늘의 시장 요약")

def arrow(pct):
    if pct is None: return "-"
    return f"🔺 {pct:.2f}%" if pct >= 0 else f"🔻 {abs(pct):.2f}%"

c1, c2, c3 = st.columns(3)
with c1:
    v = market.get("KOSPI") or {}
    st.metric("KOSPI", v.get("value","-"), arrow(v.get("change_pct")))
with c2:
    v = market.get("KOSDAQ") or {}
    st.metric("KOSDAQ", v.get("value","-"), arrow(v.get("change_pct")))
with c3:
    v = market.get("USD_KRW") or {}
    st.metric("환율(USD/KRW)", v.get("value","-"), arrow(v.get("change_pct")))

st.divider()

# =============== TOP 5 테마 ===============
st.subheader("🔥 TOP 5 테마")
top5 = themes.get("top5", [])
if top5:
    fig = px.bar(top5, x="theme", y="count", text="count")
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis_title="count", xaxis_title="theme", margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("테마 데이터 없음")

# 최신 헤드라인
st.subheader("📰 최신 헤드라인 Top 10")
heads = themes.get("headlines", [])
if heads:
    for h in heads:
        st.markdown(f"- [{h['title']}]({h['url']})")
else:
    st.info("헤드라인 없음")

st.divider()

# =============== 월간 키워드맵 ===============
st.subheader("🌐 월간 키워드맵")
kw = kmap.get("keywords", [])
if kw:
    fig2 = px.bar(kw[:30], x="keyword", y="count")  # 상위 30개까지만
    fig2.update_layout(yaxis_title="count", xaxis_title="keyword", margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("키워드 없음")
