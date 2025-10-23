# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

# 내부 모듈
from modules.style import inject_base_css, render_quick_menu, kst_now_str
from modules.market import build_ticker_items, render_ticker_line, fetch_quote, fmt_number, fmt_percent
from modules.news import (
    CATEGORIES, fetch_category_news, detect_themes, render_news_compact, THEME_STOCKS
)
from modules.ai_logic import (
    pick_promising_stocks, calc_theme_strength, calc_risk_level
)

# -------------------------------------------------------
# 기본 설정
# -------------------------------------------------------
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")
inject_base_css()
render_quick_menu()

st.markdown("## 🧠 AI 뉴스리포트")
st.caption(f"업데이트: {kst_now_str()}")

# -------------------------------------------------------
# 1) 시장 요약 (티커바)
# -------------------------------------------------------
st.markdown('<div id="mkt" class="section-anchor"></div>', unsafe_allow_html=True)
st.markdown("### 📊 오늘의 시장 요약")
colR1, colR2 = st.columns([6,1])
with colR2:
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

@st.cache_data(ttl=300)
def _ticker_items_cache():
    return build_ticker_items()

render_ticker_line(_ticker_items_cache(), speed_sec=28)
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (지연 가능)")

st.markdown("<hr/>", unsafe_allow_html=True)

# -------------------------------------------------------
# 2) 최신 뉴스 요약 (제목+시간 컴팩트)
# -------------------------------------------------------
st.markdown('<div id="news" class="section-anchor"></div>', unsafe_allow_html=True)
st.markdown("### 📰 최신 뉴스 요약")

c1, c2 = st.columns([2,1])
with c1:
    cat = st.selectbox("카테고리", list(CATEGORIES.keys()), index=0)
with c2:
    page = st.number_input("페이지", min_value=1, step=1, value=1)

@st.cache_data(ttl=600)
def _fetch_cat_news(cat_name: str):
    return fetch_category_news(cat_name, days=3, max_items=100)

news_all = _fetch_cat_news(cat)
page_size = 10
start = (page - 1) * page_size
end = start + page_size
render_news_compact(news_all[start:end], start + 1)
st.caption(f"최근 3일 · {cat} · {len(news_all)}건 중 {start+1}-{min(end, len(news_all))}")

st.markdown("<hr/>", unsafe_allow_html=True)

# -------------------------------------------------------
# 3) 뉴스 기반 테마 요약
# -------------------------------------------------------
st.markdown('<div id="themes" class="section-anchor"></div>', unsafe_allow_html=True)
st.markdown("### 🔥 뉴스 기반 테마 요약")

@st.cache_data(ttl=600)
def _fetch_all_news():
    out = []
    for c in CATEGORIES.keys():
        out += fetch_category_news(c, days=3, max_items=100)
    return out

all_news = _fetch_all_news()
theme_rows = detect_themes(all_news)  # [{'테마','뉴스건수','샘플링크','대표종목'}...]

if not theme_rows:
    st.info("최근 3일 기준 테마 신호가 약합니다.")
else:
    df_theme = pd.DataFrame(theme_rows)
    st.dataframe(df_theme, use_container_width=True, hide_index=True)

    # 상위 5개 테마 뱃지(샘플 링크 클릭 가능)
    top5 = df_theme.head(5).to_dict("records")
    if top5:
        badge_html = "<style>.tbadge{display:inline-block;margin:6px 6px 0 0;padding:6px 10px;border:1px solid #2b3a55;border-radius:10px;background:#0f1420} .tbadge b{color:#c7d2fe}</style>"
        st.markdown(badge_html, unsafe_allow_html=True)
        links = []
        for r in top5:
            if r.get("샘플링크") and r["샘플링크"] != "-":
                links.append(f"<a class='tbadge' href='{r['샘플링크']}' target='_blank'><b>{r['테마']}</b> {r['뉴스건수']}건</a>")
            else:
                links.append(f"<span class='tbadge'><b>{r['테마']}</b> {r['뉴스건수']}건</span>")
        st.markdown(" ".join(links), unsafe_allow_html=True)

st.markdown("<hr/>", unsafe_allow_html=True)

# -------------------------------------------------------
# 4) AI 상승 확률 리포트(요약 지표)
#    - 각 테마의 대표 종목 몇 개로 평균 등락률 → 강도/리스크 산출
# -------------------------------------------------------
st.markdown('<div id="rise" class="section-anchor"></div>', unsafe_allow_html=True)
st.markdown("### 📈 AI 상승 확률 예측 리포트")
report_rows = []
for row in theme_rows[:8]:
    theme = row["테마"]
    stocks = THEME_STOCKS.get(theme, [])[:4]
    deltas = []
    for _, tkr in stocks:
        try:
            last, prev = fetch_quote(tkr)
            if last and prev:
                deltas.append((last - prev) / prev * 100)
        except Exception:
            pass
    avg_delta = float(pd.Series(deltas).mean()) if deltas else 0.0
    report_rows.append({
        "테마": theme,
        "뉴스건수": row["뉴스건수"],
        "평균등락(%)": round(avg_delta, 2),
        "테마강도(1~5)": calc_theme_strength(row["뉴스건수"], avg_delta),
        "리스크(1~5)":    calc_risk_level(avg_delta),
        "대표종목": " · ".join([nm for nm, _ in THEME_STOCKS.get(theme, [])[:4]]) or "-"
    })

if report_rows:
    st.dataframe(pd.DataFrame(report_rows), use_container_width=True, hide_index=True)
else:
    st.info("대표 종목의 티커가 없어 리포트를 작성하지 못했습니다.")

st.markdown("<hr/>", unsafe_allow_html=True)

# -------------------------------------------------------
# 5) 유망 종목 Top5 (완전 자동)
# -------------------------------------------------------
st.markdown('<div id="top5" class="section-anchor"></div>', unsafe_allow_html=True)
st.markdown("### 🚀 오늘의 AI 유망 종목 Top5")

top5_df = pick_promising_stocks(theme_rows, top_n=5)
if top5_df.empty:
    st.info("추천할 종목이 없습니다. (데이터 부족/시장 변동성 낮음)")
else:
    st.dataframe(top5_df, use_container_width=True, hide_index=True)
    st.markdown("#### 🧾 AI 종합 판단")
    for _, r in top5_df.iterrows():
        emoji = "🔺" if r["등락률(%)"] > 0 else "🔻"
        st.markdown(
            f"- **{r['종목명']} ({r['티커']})** — "
            f"테마: *{r['테마']}*, 최근 등락률: **{r['등락률(%)']}%**, "
            f"뉴스빈도: {r['뉴스빈도']}건, AI점수: {r['AI점수']} {emoji}"
        )

# -------------------------------------------------------
# 바닥 주석
# -------------------------------------------------------
st.caption("※ 본 리포트는 공개 데이터를 기반으로 자동 생성되며, 투자 참고용입니다.")
