# app.py 의 테마 표 렌더 부분만 이렇게
import json, os, time
import streamlit as st
import pandas as pd
import plotly.express as px

DATA_DIR = "data"

def load_json(name):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

st.set_page_config(page_title="AI 뉴스리포트 – Web Dashboard", layout="wide")

st.title("🔥 뉴스 기반 TOP 테마")
theme_payload = load_json("theme_top5.json") or {}
theme_rows = theme_payload.get("theme_table", [])
theme_df = pd.DataFrame(theme_rows)

# 상단 바 차트
if not theme_df.empty:
    fig = px.bar(theme_df.head(5), x="theme", y="score")
    st.plotly_chart(fig, use_container_width=True)

# 상세 표 (대표 키워드)
with st.expander("상세 보기"):
    if not theme_df.empty:
        show_cols = ["theme","count","rep_keywords"]
        st.dataframe(theme_df[show_cols], use_container_width=True)
    else:
        st.info("데이터 없음")

st.header("📰 최신 헤드라인 Top 10")
headlines = load_json("headlines.json") or {}
items = headlines.get("items", [])
if items:
    for it in items:
        st.markdown(f"- [{it['title']}]({it['link']})")
else:
    st.info("헤드라인 없음")

st.header("🌐 월간 키워드맵 (최근 30일)")
kw = load_json("keyword_map.json") or {}
kw_df = pd.DataFrame(kw.get("monthly", []))
if not kw_df.empty:
    fig = px.bar(kw_df.head(25), x="keyword", y="count")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("키워드 없음")
