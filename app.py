# -*- coding: utf-8 -*-
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

# 모듈 임포트
from modules.style import apply_global_style, render_quick_menu
from modules.market import render_ticker_line
from modules.news import fetch_category_news, detect_themes, CATEGORIES
from modules.ai_logic import summarize_news, show_ai_recommendations
# (옵션) from modules.ai_logic import predict_3day

KST = ZoneInfo("Asia/Seoul")

# --------------------------------
# 페이지 설정 & 공통 스타일
# --------------------------------
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")
apply_global_style()
render_quick_menu()

# --------------------------------
# 헤더 & 리프레시
# --------------------------------
st.markdown(f"#### 🧠 AI 뉴스리포트 — 업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}")
if st.button("🔄 새로고침", help="캐시 초기화 후 화면 새로고침"):
    st.cache_data.clear()
    st.rerun()

# --------------------------------
# 실시간 지수 티커바
# --------------------------------
render_ticker_line()
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance(지연 가능)")

# --------------------------------
# 📰 최신 뉴스 요약 (컴팩트)
# --------------------------------
st.markdown('<div id="news"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 📰 최신 뉴스 요약")

categories = list(CATEGORIES.keys())  # ["경제뉴스","산업뉴스","정책뉴스", ...]
col1, col2 = st.columns([2, 1])
with col1:
    cat = st.selectbox("카테고리 선택", categories, index=0)
with col2:
    page = st.number_input("페이지", min_value=1, value=1, step=1)

news_all = fetch_category_news(cat, days=3, max_items=120)
per_page = 10
start = (page - 1) * per_page
chunk = news_all[start:start + per_page]

if not chunk:
    st.info("표시할 뉴스가 없습니다. (최근 3일 내 결과 없음)")
else:
    for it in chunk:
        st.markdown(
            f"<b><a href='{it['link']}' target='_blank'>{it['title']}</a></b><br>"
            f"<span style='color:#9aa0a6;font-size:0.85rem'>{it['time']}</span>",
            unsafe_allow_html=True,
        )
st.caption(f"최근 3일 · {cat} · 총 {len(news_all)}건 중 {start+1}-{min(start+per_page, len(news_all))} 표시")

# --------------------------------
# 🔥 뉴스 기반 테마 요약
# --------------------------------
st.markdown('<div id="themes"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🔥 뉴스 기반 테마 요약")

# 테마 감지는 더 강하게 하기 위해 모든 카테고리 합산으로 계산
all_news_3d = []
for c in categories:
    all_news_3d += fetch_category_news(c, days=3, max_items=120)

theme_rows_df = detect_themes(all_news_3d)
if theme_rows_df is None or theme_rows_df.empty:
    st.info("최근 3일 기준 테마 신호가 약합니다.")
else:
    st.dataframe(theme_rows_df, use_container_width=True, hide_index=True)

# --------------------------------
# 🧠 AI 뉴스 요약엔진
# --------------------------------
st.markdown('<div id="ai-summary"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🧠 AI 뉴스 요약엔진")
summarize_news(all_news_3d, topn_kw=10, n_sent=5)

# --------------------------------
# 📊 AI 상승 확률 예측 리포트 (앵커만 유지)
#  - 분리모듈에서는 상세 리스크 표를 생략하고,
#    유망 종목 추천 섹션에서 가격·뉴스를 종합해 제공
# --------------------------------
st.markdown('<div id="ai-risk"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 📊 AI 상승 확률 예측 리포트")
st.caption("테마 강도/리스크 산출은 유망 종목 추천 로직에 반영되어 있습니다.")

# --------------------------------
# 🚀 오늘의 AI 유망 종목 Top5
# --------------------------------
st.markdown('<div id="ai-top5"></div>', unsafe_allow_html=True)
st.divider()
show_ai_recommendations(theme_rows_df)

# --------------------------------
# 🧾 AI 종합 판단 (앵커 유지)
# --------------------------------
st.markdown('<div id="ai-judge"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🧾 AI 종합 판단")
st.caption("상단 Top5 표 아래의 코멘트가 종합 판단입니다. (뉴스빈도 × 등락률 가중)")

# --------------------------------
# 🔮 3일 예측 (옵션)
# --------------------------------
st.markdown('<div id="ai-forecast"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🔮 AI 3일 예측")
st.info("필요 시 예측 모듈을 활성화할 수 있습니다. (app.py 하단 주석 참고)")

# === (옵션) 예측 활성화 예시 ===
# from modules.ai_logic import predict_3day
# tickers = ["005930.KS", "000660.KS"]  # 예: 추천 결과의 티커 리스트를 사용
# pred_df = predict_3day(tickers)
# st.dataframe(pred_df, use_container_width=True, hide_index=True)

# --------------------------------
# 🛠 테마 관리자 (앵커만 유지)
#  - 분리 구조에서는 별도 관리자 모듈로 확장 예정
# --------------------------------
st.markdown('<div id="theme-admin"></div>', unsafe_allow_html=True)
st.divider()
st.markdown("## 🛠 테마 관리자")
st.caption("향후: 사용자 정의 키워드/핀 고정 종목을 관리하는 섹션(모듈로 확장 예정).")
