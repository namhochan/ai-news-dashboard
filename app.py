# app.py
import json, os
import pandas as pd
import streamlit as st
import plotly.express as px
from datetime import datetime

DATA_DIR = "data"

def load_json(name, default):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

st.set_page_config(page_title="AI 뉴스리포트 V27.0 – Web Dashboard", layout="wide")
st.title("📊 AI 뉴스리포트 V27.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")

# 데이터 로드
market = load_json("market_today.json", {"updated_at": None, "kospi": None, "kosdaq": None, "usdkor": None})
themes = load_json("theme_top5.json", [])
kwmap  = load_json("keyword_map.json", [])
archive= load_json("stock_archive.json", {})

st.caption(f"🕒 지표/환율 갱신: {market.get('updated_at') or '-'} (KST)")

# ======= 오늘의 시장 요약 =======
st.header("📉 오늘의 시장 요약")
m1, m2, m3 = st.columns(3)
with m1:
    v = market.get("kospi")
    st.metric(label="KOSPI", value=f"{v:,.2f}" if v else "-")
with m2:
    v = market.get("kosdaq")
    st.metric(label="KOSDAQ", value=f"{v:,.2f}" if v else "-")
with m3:
    v = market.get("usdkor")
    st.metric(label="환율(USD/KRW)", value=f"{v:,.2f}" if v else "-")
st.caption("메모: 원/달러 고평가일수록 환율 수치 ↑")

st.divider()

# ======= 테마 Top 5 =======
st.header("🔥 TOP 5 테마")
if not themes:
    st.info("테마 데이터가 없습니다. (최초 실행 직후라면 자동 업데이트를 기다려주세요)")
else:
    # 사이드바: 테마 선택 + 옵션
    st.sidebar.subheader("필터")
    theme_names = [t["theme"] for t in themes]
    selected = st.sidebar.selectbox("테마 선택", theme_names, index=0)
    show_stock_archive = st.sidebar.checkbox("종목별 전 뉴스(최신 2건) 보기", value=False)

    for t in themes:
        with st.container(border=True):
            st.subheader(f"📊 {t['theme']}")
            st.write(t["desc"])

            # 대략적 스코어 바
            st.progress(min(max(int(t.get("score", 0)), 0), 100))

            st.caption(f"대표 종목: {', '.join(t.get('stocks', []))}")

            # 관련 뉴스
            with st.expander("관련 뉴스 보기", expanded=False):
                if t.get("top_news"):
                    for i, n in enumerate(t["top_news"], 1):
                        st.markdown(f"{i}. [{n['title']}]({n['url']})")
                else:
                    st.write("관련 뉴스 없음")

            # 선택된 테마에 한해서 종목별 전 뉴스(2건)
            if show_stock_archive and selected == t["theme"]:
                st.markdown("### 📚 테마/종목 전 뉴스 (종목별 최신 2건)")
                st.caption("사이드바의 체크박스를 켜면 종목별 최신 2건을 볼 수 있습니다.")
                for s in t.get("stocks", []):
                    st.markdown(f"**- {s}**")
                    items = archive.get(s, [])
                    if not items:
                        st.write(" (뉴스 없음)")
                    else:
                        for it in items[:2]:
                            st.markdown(f"• [{it['title']}]({it['url']})")

st.divider()

# ======= 월간 키워드맵 =======
st.header("🌍 월간 키워드맵")
if not kwmap:
    st.info("키워드 데이터가 없습니다.")
else:
    df = pd.DataFrame(kwmap)
    # 상위 20개만 깔끔히
    df = df.head(20)
    fig = px.bar(df, x="keyword", y="count", title="10월 누적 주요 키워드")
    fig.update_layout(xaxis_title="키워드", yaxis_title="등장횟수")
    st.plotly_chart(fig, use_container_width=True)

# ======= 최근 헤드라인 Top 10 (테마 1순위 기준) =======
st.header("🗞️ 최근 헤드라인 Top 10")
if themes and themes[0].get("top_news"):
    for i, n in enumerate(themes[0]["top_news"][:10], 1):
        st.markdown(f"{i}. [{n['title']}]({n['url']})")
else:
    st.info("헤드라인 없음")
