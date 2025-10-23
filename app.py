import json
from datetime import datetime
import pytz
import pandas as pd
import plotly.express as px
import streamlit as st

def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}

st.set_page_config(page_title="AI 뉴스리포트 V27.0 – Web Dashboard", layout="wide")
KST = pytz.timezone("Asia/Seoul")

# 데이터 로드
market = load_json("data/market_today.json", {})
top5   = load_json("data/theme_top5.json", {"items": []})
kwmap  = load_json("data/keyword_map.json", {"items": []})
heads  = load_json("data/recent_headlines.json", {"items": []})

st.title("📊 AI 뉴스리포트 V27.0 – Web Dashboard Edition")
ts_m = market.get("timestamp_kst", "")
st.caption(f"📈 지표/환율 갱신: {ts_m or 'N/A'} (KST)")

# --- 1) 시장 요약
st.subheader("📉 오늘의 시장 요약")
cols = st.columns(3)

def fmt(v):
    return "-" if v is None else f"{v:,.2f}"

with cols[0]:
    v = market.get("KOSPI", {}).get("value")
    p = market.get("KOSPI", {}).get("pct")
    sign = "🟢" if (p or 0) >= 0 else "🔴"
    st.metric("KOSPI", fmt(v), f"{(p or 0)*100:+.2f}%")
with cols[1]:
    v = market.get("KOSDAQ", {}).get("value")
    p = market.get("KOSDAQ", {}).get("pct")
    st.metric("KOSDAQ", fmt(v), f"{(p or 0)*100:+.2f}%")
with cols[2]:
    v = market.get("USDKRW", {}).get("value")
    st.metric("환율(USD/KRW)", fmt(v))

st.divider()

# --- 2) TOP 5 테마
st.subheader("🔥 TOP 5 테마")
if top5["items"]:
    df = pd.DataFrame(top5["items"])
    fig = px.bar(df, x="theme", y="count", text="count")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("데이터 없음")

# --- 3) 월간 키워드맵
st.subheader("🌐 월간 키워드맵")
if kwmap["items"]:
    dfk = pd.DataFrame(kwmap["items"]).sort_values("count", ascending=False)
    fig2 = px.bar(dfk, x="keyword", y="count")
    st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("키워드 없음")

st.divider()

# --- 4) 최근 헤드라인
st.subheader("📰 최근 헤드라인 Top 10")
if heads["items"]:
    for a in heads["items"]:
        title = a.get("title") or "(제목 없음)"
        url = a.get("url") or "#"
        src = a.get("source") or ""
        st.markdown(f"- [{title}]({url}) — {src}")
else:
    st.info("헤드라인 없음")
