import json
import streamlit as st
import plotly.express as px
from pathlib import Path

st.set_page_config(page_title="AI 뉴스리포트 V26.0 – Web Dashboard", page_icon="📊", layout="wide")

# ---------- 유틸 ----------
def load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

# ---------- 데이터 로드 ----------
market = load_json("data/market_today.json")
themes = load_json("data/theme_top5.json")
keyword_map = load_json("data/keyword_map.json") or {}
headlines = load_json("data/headlines.json") or []

# ---------- 헤더 ----------
st.title("📊 AI 뉴스리포트 V26.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")

# ---------- 시장 요약 ----------
st.header("📉 오늘의 시장 요약")
c1, c2, c3 = st.columns(3)
def metric(col, label, key):
    val = (market or {}).get(key, "-")
    col.metric(label, val)

metric(c1, "KOSPI", "KOSPI")
metric(c2, "KOSDAQ", "KOSDAQ")
metric(c3, "환율(USD/KRW)", "USD_KRW")
if market:
    st.caption("메모: " + market.get("comment",""))

# ---------- TOP5 테마 ----------
st.header("🔥 TOP 5 테마")
if themes:
    for t in themes:
        st.subheader("📈 " + t["name"])
        st.caption(t["summary"])
        st.progress(int(t["strength"]))
        st.caption("대표 종목: " + ", ".join(t.get("stocks", [])))
        st.markdown(f"[관련 뉴스 보기]({t.get('news_link')})")
        st.divider()
else:
    st.info("테마 데이터가 아직 없습니다. 자동 업데이트 후 표시됩니다.")

# ---------- 최근 헤드라인 ----------
st.header("📰 최근 헤드라인 Top 10")
if headlines:
    for item in headlines[:10]:
        title = item.get("title","(제목없음)")
        url = item.get("url","#")
        st.markdown(f"- [{title}]({url})")
else:
    st.caption("헤드라인 데이터가 아직 없습니다. 자동 업데이트 이후 표시됩니다.")

# ---------- 월간 키워드맵 ----------
st.header("🌍 월간 키워드맵")
if keyword_map:
    items = sorted(keyword_map.items(), key=lambda x: x[1], reverse=True)
    kw, cnt = zip(*items)
    fig = px.bar(x=kw, y=cnt, labels={"x":"키워드", "y":"등장횟수"}, text=cnt)
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-30, height=420)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("키워드 데이터가 아직 없습니다.")
