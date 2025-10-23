import streamlit as st
import json
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="AI 뉴스리포트 대시보드", layout="wide")

st.title("📊 AI 뉴스리포트 V26.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

market = load_json("data/market_today.json")
themes = load_json("data/theme_top5.json")
keywords = load_json("data/keyword_map.json")

st.header("📈 오늘의 시장 요약")
col1, col2, col3 = st.columns(3)
col1.metric("KOSPI", market.get("KOSPI", "3,883.7"), "+1.56%")
col2.metric("KOSDAQ", market.get("KOSDAQ", "879.1"), "+0.76%")
col3.metric("환율", market.get("USD_KRW", "1,432"), "0.2%")

st.header("🔥 TOP 5 테마")
if themes:
    for t in themes:
        st.subheader(f"📊 {t['name']}")
        st.markdown(t.get("summary", ""))
        st.progress(t.get("strength", 50) / 100)
        st.caption("대표 종목: " + ", ".join(t.get("stocks", [])))
        if "news_link" in t:
            st.markdown(f"[관련 뉴스 보기]({t['news_link']})")
else:
    st.info("테마 데이터가 아직 없습니다. data/theme_top5.json 파일을 업데이트하세요.")

st.header("🗺️ 월간 키워드맵")
if keywords:
    fig = px.bar(
        x=list(keywords.keys()),
        y=list(keywords.values()),
        labels={'x': '키워드', 'y': '등장횟수'},
        title="10월 누적 주요 키워드"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("keyword_map.json 파일이 비어 있습니다.")

st.markdown("---")
st.caption(f"📅 마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("ⓒ 2025 AI 뉴스리포트 시스템 by namhochan")
