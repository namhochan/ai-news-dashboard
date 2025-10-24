# app.py
# 대시보드 본체 (분리 모듈 활용) + 저장(버튼/자동) 추가
# ───────────────────────────────────────────────────────────
# 변경 요약 (2025-10-24)
# 1) tzdata 없는 환경(Pyodide 등) 호환: ZoneInfo → 고정 KST(UTC+9)로 대체
# 2) 저장 기능 추가 (요청 1번: 버튼 저장, 2번: 자동 저장)
#    - 버튼: "💾 리포트 & 유망종목 저장" → CSV/JSON 생성 후 경로 표시
#    - 자동: 앱 로드 시 1회 자동 저장 (세션 상태로 중복 방지)
# 3) 기존 폴백/캐시/예외처리 유지
# ───────────────────────────────────────────────────────────

from __future__ import annotations
from datetime import datetime, timezone, timedelta
import math
import pandas as pd
import os

# ===== Streamlit Shim (없어도 폴백으로 동작) =====
try:
    import streamlit as st  # type: ignore
    STREAMLIT_AVAILABLE = True
except Exception:
    STREAMLIT_AVAILABLE = False
    class _NoOpCtx:
        def __enter__(self): return self
        def __exit__(self, a,b,c): return False
    class FakeStreamlit:
        def __init__(self): self._logs=[]
        def set_page_config(self, **k): self._logs.append(f"set_page_config({k})")
        def markdown(self, t, unsafe_allow_html=False): self._logs.append(f"md:{t[:80]}")
        def caption(self, t): self._logs.append(f"cap:{t}")
        def divider(self): self._logs.append("div")
        def columns(self, sizes): return tuple(_NoOpCtx() for _ in sizes)
        def button(self, label, **k): self._logs.append(f"btn:{label}"); return False
        def selectbox(self, label, options): self._logs.append(f"sel:{label}"); return options[0] if options else ""
        def number_input(self, *a, **k): return k.get("value",1)
        def info(self, t): self._logs.append(f"INFO:{t}")
        def warning(self, t): self._logs.append(f"WARN:{t}")
        def error(self, t): self._logs.append(f"ERR:{t}")
        def success(self, t): self._logs.append(f"OK:{t}")
        def write(self, t): self._logs.append(f"write:{t}")
        def dataframe(self, df, **k): self._logs.append(f"df:{getattr(df,'shape','?')}")
        def json(self, d, **k): self._logs.append("json")
        def expander(self, label): return _NoOpCtx()
        def text_input(self, label, value=""): return value
        class column_config:
            class LinkColumn:
                def __init__(self, label="", display_text=""): pass
        def rerun(self): self._logs.append("rerun")
        class cache_data_proxy: 
            def clear(self): pass
        cache_data = cache_data_proxy()
    st = FakeStreamlit()

# ===== 모듈 임포트 & 폴백 =====
from modules.style import inject_base_css, render_quick_menu  # type: ignore
from modules.market import build_ticker_items, fmt_number, fmt_percent  # type: ignore
try:
    from modules.market import fetch_quote  # type: ignore
except Exception:
    def fetch_quote(ticker: str): return 100.0, 98.0, {"ticker":ticker}

from modules.news import (  # type: ignore
    CATEGORIES, THEME_STOCKS, fetch_category_news, fetch_all_news, detect_themes
)
from modules.ai_logic import (
    extract_keywords, summarize_sentences,
    make_theme_report, pick_promising_by_theme_once,
    save_report_and_picks,
)  # type: ignore
from modules.analyzer import init_db, analyze_stock, load_recent  # type: ignore

# ===== KST (tzdata 없이 안전) =====
KST = timezone(timedelta(hours=9))

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
        # Streamlit 환경에서는 캐시 클리어 + 리런, 폴백에서는 무시
        try:
            st.cache_data.clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            st.rerun()
        except Exception:
            pass

# =========================
# 1) 티커바
# =========================
items = build_ticker_items()
chips = []
for it in items:
    arrow = "▲" if it.get("is_up") else ("▼" if it.get("is_down") else "•")
    cls = "up" if it.get("is_up") else ("down" if it.get("is_down") else "")
    chips.append(
        f"<span class='badge'><span class='name'>{it.get('name','')}</span>{it.get('last','-')} "
        f"<span class='{cls}'>{arrow} {it.get('pct','-')}</span></span>"
    )
line = '<span class="sep">|</span>'.join(chips)
st.markdown(
    f"<div class='ticker-wrap'><div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>",
    unsafe_allow_html=True,
)
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

# 캐시 래퍼 (모듈 내부 캐시 유무와 무관하게 안전 사용)
try:
    @st.cache_data(ttl=300)  # type: ignore[misc]
    def _fetch_category_news_cached(_cat: str, _days: int, _max: int):
        return fetch_category_news(_cat, days=_days, max_items=_max)
except Exception:
    def _fetch_category_news_cached(_cat: str, _days: int, _max: int):
        return fetch_category_news(_cat, days=_days, max_items=_max)

news_all = _fetch_category_news_cached(cat, 3, 100)
page_size = 10

# 페이지 경계 보정
try:
    total_pages = max(1, math.ceil(len(news_all)/page_size))
except Exception:
    total_pages = 1
if page > total_pages:
    st.warning(f"페이지 {int(page)}는 범위를 벗어났어요. 마지막 페이지로 이동합니다 ({total_pages}).")
    page = total_pages

start, end = (page-1)*page_size, page*page_size
for i, n in enumerate(news_all[start:end], start=start+1):
    st.markdown(
        f"<div class='news-row'><b>{i}. <a href='{n['link']}' target='_blank'>{n['title']}</a></b>"
        f"<div class='news-meta'>{n['time']}</div></div>",
        unsafe_allow_html=True,
    )
st.caption(f"최근 3일 · {cat} · {len(news_all)}건 중 {start+1}-{min(end,len(news_all))}")

st.divider()

# =========================
# 3) 뉴스 기반 테마
# =========================
st.markdown("<h2 id='sec-themes'>🔥 뉴스 기반 테마 요약</h2>", unsafe_allow_html=True)

try:
    @st.cache_data(ttl=300)  # type: ignore[misc]
    def _fetch_all_news_cached(_days: int, _per_cat: int):
        return fetch_all_news(days=_days, per_cat=_per_cat)
    @st.cache_data(ttl=120)  # type: ignore[misc]
    def _detect_themes_cached(_news):
        return detect_themes(_news)
except Exception:
    def _fetch_all_news_cached(_days: int, _per_cat: int):
        return fetch_all_news(days=_days, per_cat=_per_cat)
    def _detect_themes_cached(_news):
        return detect_themes(_news)

try:
    all_news = _fetch_all_news_cached(3, 100)
    theme_rows = _detect_themes_cached(all_news) or []
except Exception as e:
    st.error(f"테마 분석 중 오류: {e}")
    theme_rows = []

if not theme_rows:
    st.info("테마 신호가 약합니다.")
else:
    # 배지 + 테이블
    top5 = theme_rows[:5]
    st.markdown(
        " ".join([f"<span class='chip'>{r['theme']} {r['count']}건</span>" for r in top5]),
        unsafe_allow_html=True,
    )

    df_theme = pd.DataFrame(theme_rows)
    column_config = {}
    if "sample_link" in df_theme.columns:
        try:
            column_config["sample_link"] = st.column_config.LinkColumn(label="링크", display_text="바로가기")  # type: ignore[attr-defined]
        except Exception:
            pass
    st.dataframe(df_theme, use_container_width=True, hide_index=True, column_config=column_config or None)

    # 대표 종목 간단 시세(색/아이콘)
    st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")

    def _repr_price(ticker: str):
        try:
            last, prev, _ = fetch_quote(ticker)
            if last is None or prev in (None, 0):
                return "-", "-", "gray"
            delta = (last - prev) / prev * 100.0
            color = "red" if delta > 0 else ("blue" if delta < 0 else "gray")
            arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
            return fmt_number(last, 0), f"{arrow} {fmt_percent(delta)}", color
        except Exception:
            return "-", "-", "gray"

    for tr in top5:
        theme = tr.get("theme", "-")
        stocks = THEME_STOCKS.get(theme, []) or []
        if not stocks:
            continue
        st.write(f"**{theme}**")
        cols = st.columns(min(4, max(1, len(stocks))))
        for col, (name, ticker) in zip(cols, stocks[:4]):
            with col:
                px, chg, color = _repr_price(ticker)
                st.markdown(
                    f"<b>{name}</b><br><span style='color:{color}'>{px} {chg}</span><br><small>{ticker}</small>",
                    unsafe_allow_html=True,
                )
        st.markdown("<hr/>", unsafe_allow_html=True)

st.divider()

# =========================
# 4) AI 유망 종목 Top5 (테마다 1종목)
# =========================
st.markdown("<h2 id='sec-top5'>🚀 오늘의 AI 유망 종목 Top5 (테마다 1종목)</h2>", unsafe_allow_html=True)

try:
    @st.cache_data(ttl=120)  # type: ignore[misc]
    def _pick_promising_once(_theme_rows, _theme_stocks, _top_n):
        return pick_promising_by_theme_once(_theme_rows, _theme_stocks, top_n=_top_n)
except Exception:
    def _pick_promising_once(_theme_rows, _theme_stocks, _top_n):
        return pick_promising_by_theme_once(_theme_rows, _theme_stocks, top_n=_top_n)

rec_df = _pick_promising_once(theme_rows, THEME_STOCKS, 5) if theme_rows else pd.DataFrame()
if rec_df is None or rec_df.empty:
    st.info("추천할 종목이 없습니다. (유동성/이상치 필터로 제외됐을 수 있어요)")
else:
    st.dataframe(rec_df, use_container_width=True, hide_index=True)

# =========================
# 5) 저장 기능 (버튼 + 자동)
# =========================
# 저장 실행 함수

def _do_save(prefix: str = "dashboard") -> dict:
    if not theme_rows:
        raise RuntimeError("저장할 테마 데이터가 없습니다.")
    paths = save_report_and_picks(theme_rows, THEME_STOCKS, out_dir="reports", top_n=5, prefix=prefix)
    return paths

# (A) 버튼 저장
if st.button("💾 리포트 & 유망종목 저장", use_container_width=True):
    try:
        paths = _do_save(prefix="dashboard")
        st.success("저장 완료! 아래 경로를 확인하세요.")
        st.json(paths)
    except Exception as e:
        st.error(f"저장 실패: {e}")

# (B) 자동 저장 – 세션당 1회
try:
    if getattr(st, "session_state", None) is not None:
        if "__autosaved_once__" not in st.session_state and theme_rows:
            try:
                paths = _do_save(prefix="autosave")
                st.session_state["__autosaved_once__"] = True
                st.markdown("✅ 자동 저장 완료 (세션 1회)")
                st.json(paths)
            except Exception as e:
                st.warning(f"자동 저장 실패: {e}")
except Exception:
    pass

st.markdown("<h3 id='sec-judge'>🧾 AI 종합 판단</h3>", unsafe_allow_html=True)
if rec_df is not None and not rec_df.empty:
    for _, r in rec_df.iterrows():
        try:
            chg = r.get("등락률(%)")
            arrow = "" if pd.isna(chg) else ("🔺" if float(chg) >= 0 else "🔻")
            st.markdown(
                f"- **{r.get('종목명','?')} ({r.get('티커','?')})** — 테마: *{r.get('테마','?')}*, "
                f"등락률: **{('-' if pd.isna(chg) else chg)}%** {arrow}, "
                f"뉴스빈도: {int(r.get('뉴스빈도',0))}건, "
                f"AI점수: **{r.get('AI점수','-')}**, 거래량: {int(r['거래량']) if pd.notna(r.get('거래량')) else '-'}"
            )
        except Exception:
            continue

st.markdown("</div>", unsafe_allow_html=True)

# ===========================
# 🧠 종목 분석 & 기록
# ===========================
try:
    @st.cache_resource(show_spinner=False)  # type: ignore[misc]
    def _init_db_once():
        init_db(); return True
    _init_db_once()
except Exception:
    try:
        init_db()
    except Exception:
        pass

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
try:
    hist = load_recent(limit=10)
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        st.dataframe(hist, use_container_width=True, hide_index=True)
    else:
        st.info("아직 저장된 분석 기록이 없습니다.")
except Exception as e:
    st.error(f"기록 로드 중 오류: {e}")
