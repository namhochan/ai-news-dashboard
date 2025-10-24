# -*- coding: utf-8 -*-
import streamlit as st

# ---- 가장 먼저 페이지 설정 (Streamlit 규칙) ----
st.set_page_config(page_title="AI 뉴스리포트", layout="wide")

# ---- 부트 마커: 어디서 멈췄는지 보이도록 ----
st.write("BOOT-1: app.py start")

# ---- 모듈 임포트 가드: 실패하면 화면에 바로 에러 표시 ----
try:
    from modules.style import inject_base_css, render_quick_menu
    from modules.market import build_ticker_items, render_ticker_line
    from modules.news import (
        CATEGORIES, fetch_category_news, detect_themes,
        THEME_STOCKS, fetch_google_news_by_keyword
    )
    from modules.ai_logic import pick_promising_stocks_one_per_theme, make_ai_commentary
except Exception as e:
    st.error("모듈 임포트 오류가 발생했습니다. (modules/* 파일/경로/오탈자/의존성 확인)")
    st.exception(e)
    st.stop()

st.write("BOOT-2: modules imported")

# ---- 공통 CSS / 퀵메뉴 ----
inject_base_css()
render_quick_menu()

# ---- 상단: 티커바 ----
st.markdown("## 🧠 AI 뉴스리포트 – 실시간 지수 티커바")
colL, colR = st.columns([1, 5])
with colL:
    st.markdown("### 📊 시장 요약")
with colR:
    if st.button("🔄 새로고침", key="refresh"):
        st.cache_data.clear()
        st.rerun()

try:
    ticker_items = build_ticker_items()
    render_ticker_line(ticker_items, speed_sec=30)
except Exception as e:
    st.error("티커바 렌더 중 오류")
    st.exception(e)

st.divider()

# ---- 최신 뉴스(제목+일시만, 컴팩트) ----
st.markdown("<a id='sec-news'></a>", unsafe_allow_html=True)
st.markdown("## 📰 최신 뉴스 요약")

import datetime as _dt
from zoneinfo import ZoneInfo as _ZI
KST = _ZI("Asia/Seoul")
now_str = _dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)")
st.caption(f"업데이트: {now_str}")

c1, c2 = st.columns([2, 1])
with c1:
    cat = st.selectbox("📂 카테고리", list(CATEGORIES.keys()), key="news_cat")
with c2:
    page = st.number_input("페이지", min_value=1, value=1, step=1, key="news_page")

try:
    all_news = fetch_category_news(cat, days=3, max_items=100)
    page_size = 10
    s = (page - 1) * page_size
    e = s + page_size
    news_page = all_news[s:e]

    if not news_page:
        st.info("표시할 뉴스가 없습니다. (최근 3일 내 결과 없음)")
    else:
        for n in news_page:
            t = n.get("title", "").strip() or "(제목 없음)"
            when = n.get("time", "-")
            link = n.get("link", "")
            st.markdown(
                f"<div class='news-item'><a href='{link}' target='_blank'>{t}</a>"
                f"<span class='news-time'>{when}</span></div>",
                unsafe_allow_html=True,
            )
    st.caption(f"최근 3일 뉴스 총 {len(all_news)}건 · {s+1}–{min(e, len(all_news))} 표시")
except Exception as e:
    st.error("뉴스 섹션 오류")
    st.exception(e)

st.divider()

# ---- 뉴스 기반 테마 요약 ----
st.markdown("<a id='sec-themes'></a>", unsafe_allow_html=True)
st.markdown("## 🔥 뉴스 기반 테마 요약")

import pandas as pd
try:
    # 모든 카테고리 합산
    merged = []
    for _k in CATEGORIES.keys():
        merged.extend(fetch_category_news(_k, days=3, max_items=100))

    theme_rows = detect_themes(merged)  # [{theme,count,avg_delta,leaders,rep_stocks,sample_link}]
    if not theme_rows:
        st.info("테마 신호 없음.")
    else:
        # 테이블 (샘플링크는 클릭 가능하게)
        df = pd.DataFrame(theme_rows)
        if "sample_link" in df.columns:
            df["sample_link"] = df["sample_link"].fillna("").apply(
                lambda u: f"[링크]({u})" if u else "-"
            )
        st.dataframe(df, use_container_width=True, hide_index=True)
except Exception as e:
    st.error("테마 요약 섹션 오류")
    st.exception(e)

st.divider()

# ---- 유망 종목 Top5 (테마당 1종목) ----
st.markdown("<a id='sec-top5'></a>", unsafe_allow_html=True)
st.markdown("## 🚀 오늘의 AI 유망 종목 Top5 (테마당 1종목)")

try:
    recommend_df = pick_promising_stocks_one_per_theme(theme_rows, top_n=5)
    if recommend_df.empty:
        st.info("추천할 종목이 없습니다. (데이터 부족)")
    else:
        st.dataframe(recommend_df, use_container_width=True, hide_index=True)
        st.markdown("### 🧾 AI 종합 판단")
        st.markdown(make_ai_commentary(recommend_df), unsafe_allow_html=True)
except Exception as e:
    st.error("유망 종목 추천 섹션 오류")
    st.exception(e)

st.caption("※ 본 리포트는 공개 데이터를 기반으로 자동 생성된 참고 자료입니다.")
st.write("BOOT-3: render done")
