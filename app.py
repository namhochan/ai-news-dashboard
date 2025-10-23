# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

# 모듈 불러오기
from modules.style import inject_style
from modules.market import render_ticker_line
from modules.news import fetch_category_news, detect_themes
from modules.ai_logic import summarize_news, show_ai_recommendations

KST = ZoneInfo("Asia/Seoul")

# ---------------------------
# 기본 설정
# ---------------------------
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")

# ---------------------------
# 스타일 & 헤더
# ---------------------------
inject_style()
st.markdown(f"#### 🧠 AI 뉴스리포트 — 업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}")
if st.button("🔄 새로고침"):
    st.cache_data.clear()
    st.rerun()

# ---------------------------
# 실시간 지수 티커바
# ---------------------------
render_ticker_line()
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance")

# ---------------------------
# 최신 뉴스 요약
# ---------------------------
st.markdown("<div id='news'></div>", unsafe_allow_html=True)
st.divider()
st.markdown("## 📰 최신 뉴스 요약")

categories = ["경제뉴스", "산업뉴스", "정책뉴스"]
col1, col2 = st.columns([2, 1])
with col1:
    cat = st.selectbox("카테고리 선택", categories)
with col2:
    page = st.number_input("페이지", min_value=1, value=1, step=1)

news_all = fetch_category_news(cat, days=3, max_items=120)
pg_size = 10
chunk = news_all[(page-1)*pg_size:page*pg_size]
if not chunk:
    st.info("표시할 뉴스가 없습니다.")
else:
    for it in chunk:
        st.markdown(
            f"<b><a href='{it['link']}' target='_blank'>{it['title']}</a></b><br>"
            f"<span style='color:#9aa0a6;font-size:0.85rem'>{it['time']}</span>",
            unsafe_allow_html=True,
        )
st.caption(f"최근 3일 • {cat} • {len(news_all)}건 중 {(page-1)*pg_size+1}-{min(page*pg_size,len(news_all))} 표시")

# ---------------------------
# 뉴스 기반 테마 감지
# ---------------------------
st.markdown("<div id='themes'></div>", unsafe_allow_html=True)
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

theme_rows = detect_themes(news_all)
if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다.")
else:
    st.dataframe(theme_rows, use_container_width=True, hide_index=True)

# ---------------------------
# AI 요약 & 유망 종목
# ---------------------------
st.markdown("<div id='ai'></div>", unsafe_allow_html=True)
st.divider()
summarize_news(news_all)
show_ai_recommendations(theme_rows)
