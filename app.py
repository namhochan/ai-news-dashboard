import json, os
from datetime import datetime, timedelta, timezone
import streamlit as st
import pandas as pd
import plotly.express as px

KST = timezone(timedelta(hours=9))
DATA_DIR = "data"

def load_json(name, default=None):
    path = os.path.join(DATA_DIR, name)
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

st.set_page_config(page_title="AI 뉴스리포트 V26.0 – Web", layout="wide")

st.title("📊 AI 뉴스리포트 V26.0 – Web Dashboard Edition")
mt = load_json("market_today.json", {})
st.caption(f"시장지표 갱신: {mt.get('updated_at','-')} (KST)")

# ===== 오늘의 시장 요약 =====
col1, col2, col3 = st.columns(3)
def metric(col, title, d):
    with col:
        v = d.get("value")
        cp = d.get("change_pct")
        arrow = d.get("dir","")
        if v is None or cp is None:
            st.metric(title, "-", delta="데이터 없음")
        else:
            sign = "+" if cp>=0 else ""
            st.metric(title, f"{v:,}", delta=f"{arrow} {sign}{cp}%")

metric(col1, "KOSPI", mt.get("KOSPI", {}))
metric(col2, "KOSDAQ", mt.get("KOSDAQ", {}))
metric(col3, "환율(USD/KRW)", mt.get("USDKRW", {}))

st.markdown("## 🔥 TOP 5 테마")
t5 = load_json("theme_top5.json", [])
for t in t5:
    st.markdown(f"### 📈 {t['theme']}")
    st.progress(min(max(t['score'], 0), 100), text="뉴스 빈도 기반 스코어")

st.divider()

# ===== 헤드라인 Top 10 =====
st.markdown("## 🗞️ 최근 헤드라인 Top 10")
heads = load_json("recent_headlines.json", []) or []
for h in heads[:10]:
    st.markdown(f"- [{h['title']}]({h['url']})")

st.divider()

# ===== 월간 키워드맵 =====
st.markdown("## 🌍 월간 키워드맵")
kw = load_json("keyword_map.json", [])
if kw:
    df = pd.DataFrame(kw)
    fig = px.bar(df, x="keyword", y="count", text="count")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("키워드 데이터가 아직 없습니다.")
