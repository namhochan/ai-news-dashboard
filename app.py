# app.py
import json
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="AI 뉴스리포트 – Web Dashboard (RSS)", layout="wide")

DATA = Path("data")

def load_json(name, default):
    p = DATA / name
    if not p.exists(): return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default

# 데이터
market   = load_json("market_today.json", {})
topN     = load_json("theme_top.json", [])
themeAll = load_json("theme_all_table.json", [])
kwMonth  = load_json("keyword_monthly.json", [])
heads    = load_json("headlines.json", [])
emerge   = load_json("emerging_themes.json", [])

# 헤더
st.title("📊 AI 뉴스리포트 – Web Dashboard (Google News RSS)")
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
    df = pd.DataFrame(topN).sort_values("score", ascending=False)
    # 정규화 비율(%) 옵션
    norm = st.toggle("백분율로 보기", value=True)
    if norm:
        total = df["score"].sum() or 1
        df["share(%)"] = (df["score"]/total*100).round(1)
        ycol = "share(%)"
        txt = "share(%)"
    else:
        ycol = "score"; txt = "count"

    fig = px.bar(df, x="theme", y=ycol, text=txt, title=None, height=360)
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_title=None, yaxis_title=None, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("상세 보기 / 대표 종목"):
        st.dataframe(df[["theme","count","score","rep_stocks","sample_link"]], use_container_width=True, height=280)
else:
    st.info("테마 데이터 없음")

# ===== 전체 테마 =====
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
    dkm = pd.DataFrame(kwMonth).sort_values("count", ascending=False).head(20)
    fig2 = px.bar(dkm, x="keyword", y="count", height=380)
    fig2.update_layout(xaxis_tickangle=-25, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("키워드 데이터 없음")

# ===== 신규 테마 =====
st.subheader("🧪 신규 테마 감지 (바이그램)")
if emerge:
    st.dataframe(pd.DataFrame(emerge), use_container_width=True, height=260)
else:
    st.info("신규 테마 없음")

# ===== 헤드라인 =====
st.subheader("🗞️ 최신 헤드라인 Top 10")
if heads:
    for it in heads:
        st.markdown(f"- [{it['title']}]({it['link']})")
else:
    st.info("헤드라인 없음")

st.caption("※ 방법: 큰 RSS 풀을 내려받아 기사 내용을 테마 사전으로 분류 → 감쇠 점수로 순위 안정화")
