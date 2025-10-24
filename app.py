# app.py
# 대시보드 본체 (분리 모듈 활용)

from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd

from modules.style import inject_base_css, render_quick_menu
from modules.market import build_ticker_items
from modules.market import fmt_number, fmt_percent   # 재사용
from modules.news import (
    CATEGORIES, THEME_STOCKS, fetch_category_news, fetch_all_news, detect_themes
)
from modules.ai_logic import (
    extract_keywords, summarize_sentences,
    make_theme_report, pick_promising_by_theme_once
)

KST = ZoneInfo("Asia/Seoul")
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")

# ---- CSS / Quick menu ----
st.markdown(inject_base_css(), unsafe_allow_html=True)
st.markdown(render_quick_menu(), unsafe_allow_html=True)
st.markdown("<div class='compact'>", unsafe_allow_html=True)

# =========================
# 0) 헤더 & 리프레시
# =========================
c1, c2 = st.columns([5,1])
with c1:
    st.markdown("<h2 id='sec-ticker'>🧠 AI 뉴스리포트 – 실시간 지수 티커바</h2>", unsafe_allow_html=True)
    st.caption(f"업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}")
with c2:
    if st.button("🔄 새로고침", use_container_width=True):
        st.cache_data.clear(); st.rerun()

# =========================
# 1) 티커바
# =========================
items = build_ticker_items()
chips = []
for it in items:
    arrow = "▲" if it["is_up"] else ("▼" if it["is_down"] else "•")
    cls = "up" if it["is_up"] else ("down" if it["is_down"] else "")
    chips.append(f"<span class='badge'><span class='name'>{it['name']}</span>{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>")
line = '<span class="sep">|</span>'.join(chips)
st.markdown(f"<div class='ticker-wrap'><div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>", unsafe_allow_html=True)
st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (Adj Close 기준)")

st.divider()

# =========================
# 2) 최신 뉴스 (제목+시간, 컴팩트)
# =========================
st.markdown("<h2 id='sec-news'>📰 최신 뉴스 요약</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([2,1])
with col1:
    cat = st.selectbox("📂 카테고리", list(CATEGORIES.keys()))
with col2:
    page = st.number_input("페이지", min_value=1, value=1, step=1)

news_all = fetch_category_news(cat, days=3, max_items=100)
page_size = 10
start, end = (page-1)*page_size, (page)*page_size
for i, n in enumerate(news_all[start:end], start=start+1):
    st.markdown(
        f"<div class='news-row'><b>{i}. <a href='{n['link']}' target='_blank'>{n['title']}</a></b>"
        f"<div class='news-meta'>{n['time']}</div></div>",
        unsafe_allow_html=True
    )
st.caption(f"최근 3일 · {cat} · {len(news_all)}건 중 {start+1}-{min(end,len(news_all))}")

st.divider()

# =========================
# 3) 뉴스 기반 테마
# =========================
st.markdown("<h2 id='sec-themes'>🔥 뉴스 기반 테마 요약</h2>", unsafe_allow_html=True)
all_news = fetch_all_news(days=3, per_cat=100)
theme_rows = detect_themes(all_news)

if not theme_rows:
    st.info("테마 신호가 약합니다.")
else:
    # 배지 + 테이블
    top5 = theme_rows[:5]
    st.markdown(" ".join([f"<span class='chip'>{r['theme']} {r['count']}건</span>" for r in top5]), unsafe_allow_html=True)

    df_theme = pd.DataFrame(theme_rows)
    if "sample_link" in df_theme.columns:
        # 링크 클릭 가능하게 렌더링
        df_theme["sample_link"] = df_theme["sample_link"].apply(lambda u: f"[바로가기]({u})" if u else "-")
    st.dataframe(df_theme, use_container_width=True, hide_index=True)

    # 대표 종목 간단 시세(색/아이콘)
    st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")
    from modules.market import fetch_quote
    def _repr_price(ticker):
        last, prev, _ = fetch_quote(ticker)
        if not last or not prev:
            return "-", "-", "gray"
        delta = (last - prev)/prev*100.0
        color = "red" if delta > 0 else ("blue" if delta < 0 else "gray")
        arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
        return fmt_number(last,0), f"{arrow} {fmt_percent(delta)}", color

    for tr in top5:
        theme = tr["theme"]
        st.write(f"**{theme}**")
        cols = st.columns(min(4, len(THEME_STOCKS.get(theme, [])) or 1))
        for col, (name, ticker) in zip(cols, THEME_STOCKS.get(theme, [])[:4]):
            with col:
                px, chg, color = _repr_price(ticker)
                st.markdown(f"<b>{name}</b><br><span style='color:{color}'>{px} {chg}</span><br><small>{ticker}</small>", unsafe_allow_html=True)
        st.markdown("<hr/>", unsafe_allow_html=True)

st.divider()

# =========================
# 4) AI 유망 종목 Top5 (테마다 1종목)
# =========================
st.markdown("<h2 id='sec-top5'>🚀 오늘의 AI 유망 종목 Top5 (테마다 1종목)</h2>", unsafe_allow_html=True)
rec_df = pick_promising_by_theme_once(theme_rows, THEME_STOCKS, top_n=5) if theme_rows else pd.DataFrame()
if rec_df.empty:
    st.info("추천할 종목이 없습니다. (유동성/이상치 필터로 제외됐을 수 있어요)")
else:
    st.dataframe(rec_df, use_container_width=True, hide_index=True)

st.markdown("<h3 id='sec-judge'>🧾 AI 종합 판단</h3>", unsafe_allow_html=True)
if not rec_df.empty:
    for _, r in rec_df.iterrows():
        arrow = "🔺" if r["등락률(%)"] >= 0 else "🔻"
        st.markdown(
            f"- **{r['종목명']} ({r['티커']})** — 테마: *{r['테마']}*, "
            f"등락률: **{r['등락률(%)']}%** {arrow}, 뉴스빈도: {int(r['뉴스빈도'])}건, "
            f"AI점수: **{r['AI점수']}**, 거래량: {int(r['거래량']) if r['거래량'] else '-'}"
        )

st.markdown("</div>", unsafe_allow_html=True)
# (위쪽 기존 import 밑 어딘가에 추가)
from modules.analyzer import init_db, analyze_stock, load_recent

# 앱 시작 시 1회 DB 준비
init_db()

# ===========================
# 🧠 종목 분석 & 기록
# ===========================
st.divider()
st.markdown("## 🧠 종목 분석 & 기록")

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    in_name = st.text_input("종목명", value="삼성전자")
with c2:
    in_ticker = st.text_input("티커", value="005930.KS")
with c3:
    run = st.button("🔍 분석 실행", use_container_width=True)

if run:
    try:
        summary, data = analyze_stock(in_name.strip(), in_ticker.strip())
        st.success(summary)
        with st.expander("분석 원본 데이터 보기"):
            st.json(data, expanded=False)
    except Exception as e:
        st.error(f"분석 중 오류: {e}")

st.markdown("### 📁 최근 분석 기록")
hist = load_recent(limit=10)
if hist.empty:
    st.info("아직 저장된 분석 기록이 없습니다.")
else:
    st.dataframe(hist, use_container_width=True, hide_index=True)
