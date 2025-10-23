# app.py
import json
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="AI 뉴스리포트 – Web Dashboard", layout="wide")

DATA = Path("data")

def load_json(p, default):
    p = DATA / p
    if not p.exists(): return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

# 데이터 로드
market   = load_json("market_today.json", {})
topN     = load_json("theme_top.json", [])
themeAll = load_json("theme_all_table.json", [])
kwMonth  = load_json("keyword_monthly.json", [])
heads    = load_json("headlines.json", [])
emerge   = load_json("emerging_themes.json", [])

st.title("📊 AI 뉴스리포트 – Web Dashboard (RSS Auto)")
st.caption(f"지표/환율 갱신: {market.get('updated_at','-')} (KST)")

# ===== 오늘의 시장 =====
st.subheader("📉 오늘의 시장 요약")
c1,c2,c3 = st.columns(3)
with c1:
    v = market.get("KOSPI"); st.metric("KOSPI", f"{v:,.2f}" if v else "-")
with c2:
    v = market.get("KOSDAQ"); st.metric("KOSDAQ", f"{v:,.2f}" if v else "-")
with c3:
    v = market.get("USDKRW"); st.metric("환율(USD/KRW)", f"{v:,.2f}" if v else "-")

st.divider()

# ===== TOP 테마 =====
st.subheader("🔥 뉴스 기반 TOP 테마")
if topN:
    df = pd.DataFrame(topN)
    fig = px.bar(df, x="theme", y="score", text="count", title=None)
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
    with st.expander("상세 보기"):
        st.dataframe(df[["theme","count","score","rep_stocks","sample_link"]])
else:
    st.info("테마 데이터 없음")

# ===== 전체 테마 테이블 =====
st.subheader("🧭 전체 테마 집계 (감쇠 점수 포함)")
if themeAll:
    df_all = pd.DataFrame(themeAll).sort_values("score", ascending=False)
    st.dataframe(df_all, use_container_width=True, height=360)
else:
    st.info("전체 테마 데이터 없음")

st.divider()

# ===== 월간 키워드맵 =====
st.subheader("🌍 월간 키워드맵 (최근 30일)")
if kwMonth:
    dfk = pd.DataFrame(kwMonth)
    fig2 = px.bar(dfk, x="keyword", y="count")
    fig2.update_layout(xaxis_tickangle=-30)
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("키워드 데이터 없음")

# ===== 신규 테마 감지 =====
st.subheader("🧪 신규 테마 감지 (바이그램)")
if emerge:
    dfe = pd.DataFrame(emerge)
    st.dataframe(dfe, use_container_width=True, height=260)
else:
    st.info("신규 테마 없음")

# ===== 헤드라인 =====
st.subheader("🗞️ 최신 헤드라인 Top 10")
if heads:
    for it in heads:
        st.markdown(f"- [{it['title']}]({it['link']})")
else:
    st.info("헤드라인 없음")

st.caption("ⓒ Google News RSS + yfinance / 테마 감쇠: score = 0.7*이번 + 0.3*지난")
