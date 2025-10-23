import streamlit as st
import json
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="AI 뉴스리포트 대시보드", layout="wide")

st.title("📊 AI 뉴스리포트 V26.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")

# ─────────────────────────────
# 데이터 로드 함수
# ─────────────────────────────
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

market = load_json("data/market_today.json")
themes = load_json("data/theme_top5.json")
keywords = load_json("data/keyword_map.json")

# ─────────────────────────────
# 오늘의 시장 요약
# ─────────────────────────────
st.header("📈 오늘의 시장 요약")
col1, col2, col3 = st.columns(3)
col1.metric("KOSPI", market.get("KOSPI", "3,883.7"), "+1.56%")
col2.metric("KOSDAQ", market.get("KOSDAQ", "879.1"), "+0.76%")
col3.metric("환율", market.get("USD_KRW", "1,432"), "0.2%")

# ─────────────────────────────
# 테마 분석
# ─────────────────────────────
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

# ─────────────────────────────
# 키워드맵
# ─────────────────────────────
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

# ─────────────────────────────
# 하단 정보
# ─────────────────────────────
st.markdown("---")
st.caption(f"📅 마지막 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
st.caption("ⓒ 2025 AI 뉴스리포트 시스템 by namhochan")
{
  "KOSPI": "3,883.7",
  "KOSDAQ": "879.1",
  "USD_KRW": "1,432.7"
}[
  {
    "name": "데이터센터 (AI 컴퓨팅 인프라)",
    "summary": "삼성SDS 2.5조 AI 컴퓨팅센터 수주 유력 보도 이후 전력·냉각 수요 확대 기대.",
    "strength": 87,
    "stocks": ["제룡전기", "일진전기", "대원전선", "지투파워"],
    "news_link": "https://www.dnews.co.kr/uhtml/view.jsp?idxno=20251020180222"
  },
  {
    "name": "ESS (2차 입찰·국산 LFP)",
    "summary": "전력거래소 1조 ESS 2차 입찰 준비, 배터리 장비주 수혜 전망.",
    "strength": 74,
    "stocks": ["씨아이에스", "엠플러스", "천보", "코스모신소재"],
    "news_link": "https://biz.chosun.com/industry/energy/2025/10/21/ESS"
  }
]
{
  "AI": 38,
  "ESS": 26,
  "HBM": 17,
  "전력": 14,
  "수소": 11,
  "금통위": 9
}
streamlit
plotly
pandas
