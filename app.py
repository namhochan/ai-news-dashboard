import streamlit as st
import plotly.express as px
import json, os, time
from datetime import datetime
import pytz
from pathlib import Path

# ── 기본 설정
st.set_page_config(page_title="AI 뉴스리포트 V26.0 – Web Dashboard", page_icon="📊", layout="wide")
KST = pytz.timezone("Asia/Seoul")

# ── 유틸
def load_json(path):
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def fmt_mtime(path):
    try:
        ts = os.path.getmtime(path)
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
    except Exception:
        return "-"

def reltime(txt):
    """RSS/ISO 날짜를 대략적인 'n분/시간 전'으로 표시 (실패 시 빈 문자열)"""
    try:
        # NewsAPI(ISO) 우선
        if "T" in txt and "Z" in txt:
            dt = datetime.strptime(txt[:19], "%Y-%m-%dT%H:%M:%S")
            dt = KST.localize(dt)
        else:
            # RSS 포맷 다양 → 앞부분 기준 간이 파싱
            dt = datetime.strptime(txt[:25], "%a, %d %b %Y %H:%M:%S")
            dt = KST.localize(dt)
        diff = datetime.now(KST) - dt
        mins = int(diff.total_seconds() // 60)
        if mins < 1: return "방금 전"
        if mins < 60: return f"{mins}분 전"
        return f"{mins//60}시간 전"
    except Exception:
        return ""

def dedup_by_title(items, limit=50):
    seen, out = set(), []
    for it in items:
        key = (it.get("title") or "").strip().lower()
        if key and key not in seen:
            seen.add(key); out.append(it)
        if len(out) >= limit: break
    return out

# ── 데이터 로드
market      = load_json("data/market_today.json") or {}
themes      = load_json("data/theme_top5.json") or []
keyword_map = load_json("data/keyword_map.json") or {}
headlines   = load_json("data/headlines.json") or []

# ── 헤더
st.title("📊 AI 뉴스리포트 V26.0 – Web Dashboard Edition")
st.caption("자동 생성형 뉴스·테마·수급 분석 리포트 (실시간 데이터 기반)")
st.caption(f"⏱ 데이터 갱신: {fmt_mtime('data/market_today.json')} (KST)")

# ── 디버그(선택)
with st.sidebar.expander("디버그", expanded=False):
    st.write({
        "market_loaded": bool(market),
        "themes_loaded": bool(themes),
        "keyword_map_len": len(keyword_map),
        "headlines_len": len(headlines),
    })

# ── 오늘의 시장 요약
st.header("📉 오늘의 시장 요약")
c1, c2, c3 = st.columns(3)
c1.metric("KOSPI",  market.get("KOSPI", "-"))
c2.metric("KOSDAQ", market.get("KOSDAQ", "-"))
c3.metric("환율(USD/KRW)", market.get("USD_KRW", "-"))
if market:
    st.caption("메모: " + market.get("comment", ""))

# ── TOP 5 테마
st.header("🔥 TOP 5 테마")
if themes:
    for t in themes:
        st.subheader("📈 " + t.get("name", "테마"))
        st.caption(t.get("summary", ""))
        st.progress(int(t.get("strength", 60)))
        stocks = t.get("stocks", [])
        if stocks:
            st.caption("대표 종목: " + ", ".join(stocks))
        st.link_button("관련 뉴스 보기", t.get("news_link", "https://news.google.com/?hl=ko&gl=KR&ceid=KR:ko"))
        st.divider()
else:
    st.info("테마 데이터가 아직 없습니다. 자동 업데이트 후 표시됩니다.")

# ── 최근 헤드라인
st.header("📰 최근 헤드라인 Top 10")
filtered = dedup_by_title(headlines, limit=50)

# 사이드바 키워드 필터
query = st.sidebar.text_input("헤드라인 필터(키워드)", "")
if query:
    filtered = [x for x in filtered if query.lower() in (x.get("title","").lower())]

if filtered:
    for item in filtered[:10]:
        title = item.get("title","(제목없음)")
        url   = item.get("url","#")
        src   = item.get("source","")
        when  = reltime(item.get("published",""))
        meta  = " · ".join([x for x in [src, when] if x])
        st.markdown(f"- [{title}]({url})  \n  <span style='color:#9aa0a6;font-size:90%'>{meta}</span>", unsafe_allow_html=True)

    with st.expander("더 보기 (11~30)"):
        for item in filtered[10:30]:
            title = item.get("title","(제목없음)")
            url   = item.get("url","#")
            src   = item.get("source","")
            when  = reltime(item.get("published",""))
            meta  = " · ".join([x for x in [src, when] if x])
            st.markdown(f"- [{title}]({url})  \n  <span style='color:#9aa0a6;font-size:90%'>{meta}</span>", unsafe_allow_html=True)
else:
    st.caption("헤드라인 데이터가 아직 없습니다. 자동 업데이트 이후 표시됩니다.")

# ── 월간 키워드맵
st.header("🌍 월간 키워드맵")
if keyword_map:
    items = sorted(keyword_map.items(), key=lambda x: x[1], reverse=True)[:15]  # 상위 15개로 가독성 향상
    kw, cnt = zip(*items)
    fig = px.bar(x=kw, y=cnt, labels={"x":"키워드","y":"등장횟수"}, text=cnt)
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-30, height=420, margin=dict(l=10,r=10,t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("키워드 데이터가 아직 없습니다.")
