# -*- coding: utf-8 -*-
# app.py - AI 뉴스 + 테마 기반 자동 리포트 대시보드
# Streamlit 안전 실행 버전 (v3.7.1+R)

import streamlit as st
import pandas as pd
import traceback
from datetime import datetime

# 내부 모듈 임포트 (없는 경우 폴백 처리)
try:
    from modules.style import inject_base_css, render_quick_menu
    from modules.market import build_ticker_items
    from modules.news import fetch_all_news, detect_themes
    from modules.ai_logic import make_theme_report, pick_promising_by_theme_once
except Exception as e:
    st.error("❌ 내부 모듈 불러오기 실패:\n" + str(e))
    st.stop()

# -------------------------------------------------------------------
# 0 - 페이지 기본 설정
# -------------------------------------------------------------------
st.set_page_config(
    page_title="AI 뉴스리포트 자동 테마분석",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(inject_base_css(), unsafe_allow_html=True)
st.markdown(render_quick_menu(), unsafe_allow_html=True)

# -------------------------------------------------------------------
# 1 - 헤더 & 새로고침 버튼
# -------------------------------------------------------------------
col1, col2 = st.columns([5, 1])
with col1:
    st.title("🧠 AI 뉴스 기반 테마 리포트")
with col2:
    st.button("🔄 새로고침", on_click=lambda: st.experimental_rerun())

st.markdown("---")

# -------------------------------------------------------------------
# 2 - 뉴스 수집 & 테마 감지
# -------------------------------------------------------------------
st.subheader("📰 뉴스 기반 구성 요약")
st.caption("뉴스 본문/제목에서 키워드를 추출하고, 자동 테마 감지→추천까지 한 번에 구성합니다.")

try:
    with st.spinner("⏳ 구글 뉴스 수집 중..."):
        all_news = fetch_all_news(days=3, per_cat=100)
    st.success(f"✅ 수집된 뉴스 {len(all_news)}건")
except Exception as e:
    st.warning("⚠️ 뉴스 수집 실패. 네트워크 문제이거나 RSS 차단일 수 있습니다.")
    st.text(str(e))
    all_news = []

if all_news:
    themes = detect_themes(all_news)
    st.markdown("#### 🔍 자동 키워드(Top 15)")
    chips = [f"<span class='chip'>{r['theme']} {r['count']}</span>" for r in themes[:15]]
    st.markdown(" ".join(chips), unsafe_allow_html=True)

    df_theme = pd.DataFrame(themes)
    st.dataframe(df_theme, use_container_width=True)

# -------------------------------------------------------------------
# 3 - 테마별 종목 시세 요약
# -------------------------------------------------------------------
st.markdown("### 📊 대표 시세 (상승=빨강 / 하락=파랑)")

try:
    items = build_ticker_items()
    cols = st.columns(4)
    for i, it in enumerate(items):
        with cols[i % 4]:
            color = "#e66" if it["is_up"] else "#6aa2ff"
            st.markdown(f"**{it['name']}**<br>"
                        f"<span style='color:{color}'>{it['last']} ({it['pct']})</span>",
                        unsafe_allow_html=True)
except Exception as e:
    st.error("시세 데이터 로딩 실패: " + str(e))

# -------------------------------------------------------------------
# 4 - 테마 강도 & 유망 종목 추천
# -------------------------------------------------------------------
st.markdown("### 🚀 테마 강도 및 유망 종목 추천")

try:
    import numpy as np
    from modules.news import THEME_STOCKS

    theme_report = make_theme_report(themes, THEME_STOCKS)
    st.dataframe(theme_report, use_container_width=True)

    picks = pick_promising_by_theme_once(themes, THEME_STOCKS)
    st.subheader("🎯 유망 종목 Top5")
    st.dataframe(picks, use_container_width=True)

except Exception as e:
    st.warning("유망 종목 계산 중 오류 발생")
    st.text(traceback.format_exc())

# -------------------------------------------------------------------
# 5 - 저장 기능 (자동 리포트)
# -------------------------------------------------------------------
def save_report_and_picks(theme_df, picks_df):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    import os
    os.makedirs("reports", exist_ok=True)

    report_csv = f"reports/autosave_theme_report_{now}.csv"
    report_json = f"reports/autosave_theme_report_{now}.json"
    picks_csv = f"reports/autosave_promising_picks_{now}.csv"
    picks_json = f"reports/autosave_promising_picks_{now}.json"

    theme_df.to_csv(report_csv, index=False)
    theme_df.to_json(report_json, force_ascii=False, orient="records", indent=2)
    picks_df.to_csv(picks_csv, index=False)
    picks_df.to_json(picks_json, force_ascii=False, orient="records", indent=2)
    return {
        "report_csv": report_csv,
        "report_json": report_json,
        "picks_csv": picks_csv,
        "picks_json": picks_json,
    }

if st.button("💾 리포트 & 유망종목 저장"):
    if 'theme_report' in locals() and 'picks' in locals():
        paths = save_report_and_picks(theme_report, picks)
        st.json(paths)
    else:
        st.warning("먼저 뉴스 분석을 실행해주세요.")

# -------------------------------------------------------------------
# 6 - 푸터
# -------------------------------------------------------------------
st.markdown("---")
st.caption("© 2025 AI News Dashboard v3.7.1+R | Streamlit 안전 버전")
