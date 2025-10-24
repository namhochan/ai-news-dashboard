-- coding: utf-8 --

app.py - dashboard main (safe for Streamlit / no tzdata dependency)

v3.7.1+R

from future import annotations from datetime import datetime, timezone, timedelta import os import json import pandas as pd import streamlit as st

---- internal modules ----

from modules.style import inject_base_css, render_quick_menu from modules.market import build_ticker_items, fmt_number, fmt_percent, fetch_quote from modules.news import ( CATEGORIES, THEME_STOCKS, fetch_category_news, fetch_all_news, detect_themes, ) from modules.ai_logic import ( extract_keywords, summarize_sentences, make_theme_report, pick_promising_by_theme_once, ) from modules.analyzer import init_db, analyze_stock, load_recent

fixed KST (UTC+9) - no ZoneInfo/tzdata needed

KST = timezone(timedelta(hours=9))

------------------------------------------------------

page setup

------------------------------------------------------

st.set_page_config(page_title="AI 뉴스리포트 - 자동 테마·시세 예측", layout="wide") st.markdown(inject_base_css(), unsafe_allow_html=True) st.markdown(render_quick_menu(), unsafe_allow_html=True) st.markdown("<div class='compact'>", unsafe_allow_html=True)

session state

if "autosaved_once" not in st.session_state: st.session_state["autosaved_once"] = False

------------------------------------------------------

fallback: save_report_and_picks (if not provided in ai_logic)

------------------------------------------------------

try: from modules.ai_logic import save_report_and_picks  # type: ignore except Exception: def save_report_and_picks(theme_rows, theme_stocks, out_dir="reports", top_n=5, prefix="export"): os.makedirs(out_dir, exist_ok=True) ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S") report_csv = os.path.join(out_dir, f"{prefix}theme_report{ts}.csv") report_json = os.path.join(out_dir, f"{prefix}theme_report{ts}.json") pd.DataFrame(theme_rows).to_csv(report_csv, index=False, encoding="utf-8") with open(report_json, "w", encoding="utf-8") as f: json.dump(theme_rows, f, ensure_ascii=False) picks_df = pick_promising_by_theme_once(theme_rows, theme_stocks, top_n=top_n) picks_csv = os.path.join(out_dir, f"{prefix}promising_picks{ts}.csv") picks_json = os.path.join(out_dir, f"{prefix}promising_picks{ts}.json") if not picks_df.empty: picks_df.to_csv(picks_csv, index=False, encoding="utf-8") with open(picks_json, "w", encoding="utf-8") as f: json.dump(picks_df.to_dict(orient="records"), f, ensure_ascii=False) else: open(picks_csv, "a", encoding="utf-8").close() open(picks_json, "a", encoding="utf-8").close() return { "report_csv": report_csv, "report_json": report_json, "picks_csv": picks_csv, "picks_json": picks_json, }

------------------------------------------------------

cached safe wrappers for news fetch

------------------------------------------------------

@st.cache_data(ttl=600) def _safe_fetch_category_news(cat, days=3, max_items=100): try: return fetch_category_news(cat, days=days, max_items=max_items) except Exception: return []

@st.cache_data(ttl=600) def _safe_fetch_all_news(days=3, per_cat=100): try: return fetch_all_news(days=days, per_cat=per_cat) except Exception: return []

------------------------------------------------------

0 - header and refresh

------------------------------------------------------

c1, c2 = st.columns([5, 1]) with c1: st.markdown("<h2 id='sec-ticker'>🧠 AI 뉴스리포트 - 실시간 지수 티커바</h2>", unsafe_allow_html=True) st.caption(datetime.now(KST).strftime("업데이트: %Y-%m-%d %H:%M:%S (KST)")) with c2: if st.button("🔄 새로고침", use_container_width=True): st.cache_data.clear(); st.rerun()

------------------------------------------------------

1 - ticker bar

------------------------------------------------------

items = build_ticker_items() chips: List[str] = []  # type: ignore[name-defined] for it in items: arrow = "▲" if it["is_up"] else ("▼" if it["is_down"] else "•") cls = "up" if it["is_up"] else ("down" if it["is_down"] else "") chips.append( f"<span class='badge'><span class='name'>{it['name']}</span>{it['last']} <span class='{cls}'>{arrow} {it['pct']}</span></span>" ) line = '<span class="sep">|</span>'.join(chips) st.markdown( f"<div class='ticker-wrap'><div class='ticker-track'>{line}<span class='sep'>|</span>{line}</div></div>", unsafe_allow_html=True, ) st.caption("※ 상승=빨강, 하락=파랑 · 데이터: Yahoo Finance (Adj Close 기반, 폴백 가능)")

st.divider()

------------------------------------------------------

2 - latest news (compact)

------------------------------------------------------

st.markdown("<h2 id='sec-news'>📰 최신 뉴스 요약</h2>", unsafe_allow_html=True) col1, col2 = st.columns([2, 1]) with col1: cat = st.selectbox("📂 카테고리", list(CATEGORIES.keys())) with col2: page = st.number_input("페이지", min_value=1, value=1, step=1)

news_all = _safe_fetch_category_news(cat, days=3, max_items=100)

page_size = 10 start, end = (page - 1) * page_size, page * page_size for i, n in enumerate(news_all[start:end], start=start + 1): title = n.get("title", "-") link = n.get("link", "#") when = n.get("time", "-") st.markdown( f"<div class='news-row'><b>{i}. <a href='{link}' target='_blank' rel='noreferrer noopener'>{title}</a></b>" f"<div class='news-meta'>{when}</div></div>", unsafe_allow_html=True, ) st.caption(f"최근 3일 · {cat} · {len(news_all)}건 중 {start+1}-{min(end, len(news_all))}")

st.divider()

------------------------------------------------------

3 - themes from news

------------------------------------------------------

st.markdown("<h2 id='sec-themes'>🔥 뉴스 기반 테마 요약</h2>", unsafe_allow_html=True) all_news = _safe_fetch_all_news(days=3, per_cat=100)

theme_rows = detect_themes(all_news)

if not theme_rows: st.info("테마 신호가 약합니다. (네트워크 차단/빈 데이터일 수 있어요)") else: top5 = theme_rows[:5] st.markdown( " ".join([f"<span class='chip'>{r['theme']} {r['count']}건</span>" for r in top5]), unsafe_allow_html=True, )

df_theme = pd.DataFrame(theme_rows)
if "sample_link" in df_theme.columns:
    df_theme["sample_link"] = df_theme["sample_link"].apply(lambda u: f"[바로가기]({u})" if u else "-")
st.dataframe(df_theme, use_container_width=True, hide_index=True)

st.markdown("### 🧩 대표 종목 시세 (상승=빨강 / 하락=파랑)")

def _repr_price(ticker: str):
    last, prev, _ = fetch_quote(ticker)
    if not last or not prev:
        return "-", "-", "gray"
    delta = (last - prev) / prev * 100.0
    color = "red" if delta > 0 else ("blue" if delta < 0 else "gray")
    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "■")
    return fmt_number(last, 0), f"{arrow} {fmt_percent(delta)}", color

for tr in top5:
    theme = tr["theme"]
    st.write(f"**{theme}**")
    stocks = THEME_STOCKS.get(theme, [])
    cols = st.columns(min(4, len(stocks) or 1))
    for col, (name, ticker) in zip(cols, stocks[:4]):
        with col:
            px, chg, color = _repr_price(ticker)
            st.markdown(
                f"<b>{name}</b><br><span style='color:{color}'>{px} {chg}</span><br><small>{ticker}</small>",
                unsafe_allow_html=True,
            )
    st.markdown("<hr/>", unsafe_allow_html=True)

st.divider()

------------------------------------------------------

4 - top5 picks (one per theme)

------------------------------------------------------

st.markdown("<h2 id='sec-top5'>🚀 오늘의 AI 유망 종목 Top5 (테마다 1종목)</h2>", unsafe_allow_html=True) rec_df = pick_promising_by_theme_once(theme_rows, THEME_STOCKS, top_n=5) if theme_rows else pd.DataFrame() if rec_df.empty: st.info("추천할 종목이 없습니다. (유동성/이상치 필터로 제외됐을 수 있어요)") else: st.dataframe(rec_df, use_container_width=True, hide_index=True)

st.markdown("<h3 id='sec-judge'>🧾 AI 종합 판단</h3>", unsafe_allow_html=True) if not rec_df.empty: for _, r in rec_df.iterrows(): try: pct = float(r.get("등락률(%)", 0)) except Exception: pct = 0.0 arrow = "🔺" if pct >= 0 else "🔻" st.markdown( f"- {r.get('종목명')} ({r.get('티커')}) — 테마: {r.get('테마')}, " f"등락률: {r.get('등락률(%)')}% {arrow}, 뉴스빈도: {int(r.get('뉴스빈도', 0))}건, " f"AI점수: {r.get('AI점수')}, 거래량: {int(r.get('거래량')) if r.get('거래량') else '-'}" )

st.divider()

------------------------------------------------------

5 - save (one-click/manual/auto) + download buttons

------------------------------------------------------

def _render_downloads(paths: dict): try: for label, p in (paths or {}).items(): if not p or not os.path.isfile(p): continue with open(p, "rb") as f: data = f.read() fname = os.path.basename(p) st.download_button( label=f"⬇️ {label} 다운로드 ({fname})", data=data, file_name=fname, mime=( "text/csv" if fname.lower().endswith(".csv") else "application/json" if fname.lower().endswith(".json") else "application/octet-stream" ), use_container_width=True, ) except Exception as e: st.warning(f"다운로드 버튼 생성 실패: {e}")

def _do_save(prefix: str = "dashboard") -> dict: if not theme_rows: raise RuntimeError("저장할 테마 데이터가 없습니다.") out = save_report_and_picks(theme_rows, THEME_STOCKS, out_dir="reports", top_n=5, prefix=prefix) return out

st.markdown("### 🪄 한번에 분석+추천+저장") cc1, cc2 = st.columns([1, 2]) with cc1: if st.button("🪄 한번에 분석+추천+저장", use_container_width=True): if not theme_rows: st.warning("테마 신호가 약해 저장을 건너뜁니다.") else: try: paths = _do_save(prefix="oneclick") st.success("완료! 아래에서 파일을 바로 내려받을 수 있어요.") st.json(paths) _render_downloads(paths) except Exception as e: st.error(f"원클릭 처리 실패: {e}") with cc2: st.caption("* 뉴스→테마 감지→유망종목 추천→CSV/JSON 저장까지 한 번에 실행")

st.markdown("### 🗂️ 리포트 & 유망종목 저장") if st.button("💾 리포트 & 유망종목 저장", use_container_width=True): try: paths = _do_save(prefix="manual") st.success("저장 완료! 아래 파일을 바로 다운로드 할 수 있어요.") st.json(paths) _render_downloads(paths) except Exception as e: st.error(f"저장 실패: {e}")

session one-time autosave

if not st.session_state.get("autosaved_once") and theme_rows: try: paths = _do_save(prefix="autosave") st.session_state["autosaved_once"] = True st.markdown("✅ 자동 저장 완료 (세션 1회)") st.json(paths) _render_downloads(paths) except Exception as e: st.warning(f"자동 저장 실패: {e}")

st.divider()

------------------------------------------------------

6 - stock analyze and history

------------------------------------------------------

st.markdown("## 🧠 종목 분석 & 기록")

c1, c2, c3 = st.columns([2, 2, 1]) with c1: in_name = st.text_input("종목명", value="삼성전자") with c2: in_ticker = st.text_input("티커", value="005930.KS") with c3: run = st.button("🔍 분석 실행", use_container_width=True)

init_db()

if run: try: summary, data = analyze_stock(in_name.strip(), in_ticker.strip()) st.success(summary) with st.expander("분석 원본 데이터 보기"): st.json(data, expanded=False) except Exception as e: st.error(f"분석 중 오류: {e}")

st.markdown("### 📁 최근 분석 기록") hist = load_recent(limit=10) if hist.empty: st.info("아직 저장된 분석 기록이 없습니다.") else: st.dataframe(hist, use_container_width=True, hide_index=True)

------------------------------------------------------

7 - saved files explorer and debug (optional)

------------------------------------------------------

with st.expander("📂 저장 파일 탐색기"): base_dirs = ["reports", "보고서", "data"] for d in base_dirs: st.write(f"{d}") try: if not os.path.isdir(d): st.caption("(디렉터리 없음)") continue files = sorted(os.listdir(d)) if not files: st.caption("(파일 없음)") continue for fn in files: p = os.path.join(d, fn) if not os.path.isfile(p): continue size = os.path.getsize(p) st.write(f"- {fn} — {size} bytes") try: with open(p, "rb") as f: buf = f.read() st.download_button( label=f"⬇️ 다운로드: {fn}", data=buf, file_name=fn, mime=("text/csv" if fn.lower().endswith(".csv") else "application/json" if fn.lower().endswith(".json") else "application/octet-stream"), key=f"dl_{d}_{fn}", ) except Exception: pass except Exception as e: st.warning(f"목록 조회 실패: {e}")

with st.expander("🪵 디버그(경로/DB)"): st.write("cwd:", os.getcwd()) st.write("reports exists:", os.path.isdir("reports")) st.write("data exists:", os.path.isdir("data"))

st.markdown("</div>", unsafe_allow_html=True)
