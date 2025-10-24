# app.py
# 대시보드 본체 (샌드박스/Streamlit 미설치/모듈 부재 환경 호환) + 저장(버튼/자동) + 원클릭 추천
# v3.7.1+3

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple, Optional
import math
import os
import pandas as pd

# ==========================================================
# 0) Streamlit Shim (없어도 폴백으로 동작) — f-string 백슬래시 안전 처리 포함
# ==========================================================
try:
    import streamlit as st  # type: ignore
    STREAMLIT_AVAILABLE = True
except Exception:
    STREAMLIT_AVAILABLE = False

    class _NoOpCtx:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    class FakeStreamlit:
        def __init__(self):
            self._logs: List[str] = []
            self.session_state: Dict[str, Any] = {}
        # --- helpers ---
        @staticmethod
        def _safe_preview(text: Any, limit: int = 120) -> str:
            try:
                s = str(text)
            except Exception:
                s = ""
            # f-string 내부에 백슬래시가 들어가지 않도록 사전 정제
            s = s.replace("\n", " ").replace("\r", " ")
            return s[:limit]
        # layout & widgets
        def set_page_config(self, **k): self._logs.append(f"set_page_config({k})")
        def markdown(self, t, unsafe_allow_html=False):
            safe = self._safe_preview(t)
            self._logs.append(f"md:{safe}")
        def caption(self, t):
            safe = self._safe_preview(t)
            self._logs.append(f"cap:{safe}")
        def divider(self): self._logs.append("div")
        def columns(self, sizes): return tuple(_NoOpCtx() for _ in sizes)
        def button(self, label, **k):
            safe = self._safe_preview(label)
            self._logs.append(f"btn:{safe}")
            return False
        def selectbox(self, label, options):
            safe = self._safe_preview(label)
            self._logs.append(f"sel:{safe}")
            return options[0] if options else ""
        def number_input(self, label, min_value=0, value=0, step=1):
            safe = self._safe_preview(label)
            self._logs.append(f"num:{safe}")
            return value
        def text_input(self, label, value=""):
            safe = self._safe_preview(label)
            self._logs.append(f"txt:{safe}")
            return value
        def write(self, t):
            safe = self._safe_preview(t)
            self._logs.append(f"write:{safe}")
        def info(self, t):
            safe = self._safe_preview(t)
            self._logs.append(f"INFO:{safe}")
        def warning(self, t):
            safe = self._safe_preview(t)
            self._logs.append(f"WARN:{safe}")
        def error(self, t):
            safe = self._safe_preview(t)
            self._logs.append(f"ERR:{safe}")
        def success(self, t):
            safe = self._safe_preview(t)
            self._logs.append(f"OK:{safe}")
        def dataframe(self, df, **k): self._logs.append(f"df:{getattr(df,'shape','?')}")
        def json(self, d, **k): self._logs.append("json")
        def expander(self, label): return _NoOpCtx()
        class column_config:
            class LinkColumn:
                def __init__(self, label: str = "", display_text: str = ""): ...
        class cache_data_proxy:
            def clear(self): ...
        cache_data = cache_data_proxy()
        def rerun(self): self._logs.append("rerun")

    st = FakeStreamlit()

# ==========================================================
# 1) tzdata 없이 안전한 KST (UTC+9 고정)
# ==========================================================
KST = timezone(timedelta(hours=9))

# ==========================================================
# 2) 외부 modules.* 폴백 (style / market / news / ai_logic / analyzer)
# ==========================================================
# style
try:
    from modules.style import inject_base_css, render_quick_menu  # type: ignore
except Exception:
    def inject_base_css() -> str:
        return """
        <style>
          .compact{max-width:1200px;margin:0 auto}
          .badge{padding:4px 8px;border-radius:12px;background:#111;color:#eee;margin-right:8px}
          .badge .name{font-weight:600;margin-right:6px}
          .up{color:#e30000}.down{color:#0050ff}.sep{opacity:.3;margin:0 10px}
          .ticker-wrap{overflow:hidden;white-space:nowrap}
          .ticker-track{display:inline-block;animation:ticker 20s linear infinite}
          @keyframes ticker{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
          .chip{display:inline-block;background:#f1f3f5;border-radius:999px;padding:4px 10px;margin:2px}
          .news-row{padding:6px 0;border-bottom:1px solid #eee}
          .news-meta{color:#666;font-size:12px}
        </style>
        """
    def render_quick_menu() -> str:
        return ""

# market
try:
    from modules.market import build_ticker_items, fmt_number, fmt_percent, fetch_quote  # type: ignore
except Exception:
    def fmt_number(x: Optional[float], ndigits: int = 0) -> str:
        if x is None:
            return "-"
        try:
            return f"{x:,.{ndigits}f}"
        except Exception:
            return str(x)
    def fmt_percent(x: Optional[float]) -> str:
        if x is None:
            return "-"
        try:
            return f"{x:.2f}%"
        except Exception:
            return str(x)
    def build_ticker_items() -> List[Dict[str, Any]]:
        return [
            {"name":"KOSPI","last":"2,450.12","pct":"+0.42%","is_up":True,"is_down":False},
            {"name":"KOSDAQ","last":"800.50","pct":"-0.31%","is_up":False,"is_down":True},
            {"name":"USD/KRW","last":"1,355.2","pct":"+0.05%","is_up":True,"is_down":False},
        ]
    def fetch_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Any]:
        seed = sum(ord(c) for c in ticker) % 100
        last = 100.0 + (seed - 50) * 0.25
        prev = last * (1.0 - ((seed % 7) - 3) * 0.006)
        vol = 60_000 + seed * 500
        return float(last), float(prev), int(vol)

# news
try:
    from modules.news import (  # type: ignore
        CATEGORIES, THEME_STOCKS, fetch_category_news, fetch_all_news, detect_themes
    )
except Exception:
    CATEGORIES = {
        "세계": ["AI","연준","원자재","환율"],
        "국내": ["정책","반도체","로봇","2차전지"],
        "산업": ["로봇","자동차","에너지","데이터센터"],
        "정책": ["예산","세제","규제완화","수출"],
    }
    THEME_STOCKS = {
        "AI": [("솔루스첨단소재","336370.KS"),("삼성전자","005930.KS")],
        "로봇": [("나우로보틱스","277810.KQ"),("유진로봇","056080.KQ")],
        "데이터센터": [("삼성SDS","018260.KS"),("효성중공업","298040.KS")],
    }
    def _mock_news_item(i: int) -> Dict[str, Any]:
        return {"title": f"폴백 뉴스 제목 {i}", "link": f"https://example.com/news/{i}", "time": datetime.now(KST).strftime("%Y-%m-%d %H:%M")}
    def fetch_category_news(cat: str, days: int = 3, max_items: int = 100):
        return [_mock_news_item(i) for i in range(1, min(max_items, 25)+1)]
    def fetch_all_news(days: int = 3, per_cat: int = 100):
        out: List[Dict[str, Any]] = []
        for c in CATEGORIES:
            out.extend(fetch_category_news(c, days=days, max_items=min(per_cat, 20)))
        return out
    def detect_themes(all_news: List[Dict[str, Any]]):
        return [
            {"theme":"AI","count":12,"sample_link":"https://example.com/ai"},
            {"theme":"로봇","count":9,"sample_link":"https://example.com/robot"},
            {"theme":"데이터센터","count":7,"sample_link":"https://example.com/dc"},
        ]

# ai_logic
try:
    from modules.ai_logic import (  # type: ignore
        extract_keywords, summarize_sentences,
        make_theme_report, pick_promising_by_theme_once,
        save_report_and_picks,
    )
except Exception:
    import re, json
    import numpy as np
    def extract_keywords(titles, topn=10):
        words = []
        for t in titles:
            t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t or "")
            words.extend([w for w in t.split() if len(w) >= 2])
        from collections import Counter
        return [w for w, _ in Counter(words).most_common(topn)]
    def summarize_sentences(texts, n_sent=5):
        if not texts: return []
        full = " ".join(texts)
        sents = re.split(r'[.!?]\s+', full)
        sents = [s.strip() for s in sents if len(s.strip()) > 20]
        scores = {s: sum(w in full for w in s.split()) for s in sents}
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [s for s,_ in ranked[:n_sent]]
    MAX_ABS_MOVE, OUTLIER_DROP, MIN_VOLUME = 25.0, 35.0, 30_000
    def _safe_delta_pct(ticker: str):
        last, prev, vol = fetch_quote(ticker)
        if last in (None,) or prev in (None,0): return None
        pct = (last - prev)/prev*100.0
        if vol is not None and vol < MIN_VOLUME: return None
        if abs(pct) > OUTLIER_DROP: return None
        pct_for_score = float(np.clip(pct, -MAX_ABS_MOVE, MAX_ABS_MOVE))
        return pct, pct_for_score, vol
    def pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=5):
        sel = []
        for tr in theme_rows:
            theme, freq = tr.get("theme"), tr.get("count",0)
            best = None
            for name, ticker in theme_stocks_map.get(theme, []):
                res = _safe_delta_pct(ticker)
                if res is None: continue
                real_pct, score_pct, vol = res
                freq_score = min(freq/20.0, 1.0)
                score = freq_score*0.4 + (score_pct/MAX_ABS_MOVE)*0.6
                cand = {"테마":theme, "종목명":name, "티커":ticker, "등락률(%)":round(real_pct,2), "뉴스빈도":int(freq), "AI점수":round(score*100,2), "거래량":vol}
                if best is None or cand["AI점수"]>best["AI점수"]: best=cand
            if best: sel.append(best)
            if len(sel)>=top_n: break
        sel.sort(key=lambda x: x["AI점수"], reverse=True)
        return pd.DataFrame(sel)
    def make_theme_report(theme_rows, theme_stocks_map):
        rows=[]
        import numpy as np
        for tr in theme_rows[:8]:
            theme = tr.get("theme"); cnt=int(tr.get("count",0))
            deltas=[]
            for _,t in theme_stocks_map.get(theme,[]):
                last, prev, _ = fetch_quote(t)
                if last is not None and prev not in (None,0):
                    deltas.append((last-prev)/prev*100.0)
            avg = float(np.mean(deltas)) if deltas else 0.0
            def _strength(c,a):
                freq = min(max(c/20.0,0.0),1.0); price=min(max((a+5)/10.0,0.0),1.0)
                return round((freq*0.6+price*0.4)*5.0,1)
            def _risk(a):
                return 1 if a>=3 else 2 if a>=1 else 3 if a>=-1 else 4 if a>=-3 else 5
            rows.append({"테마":theme,"뉴스건수":cnt,"평균등락(%)":round(avg,2),"테마강도(1~5)":_strength(cnt,avg),"AI리스크(1~5)":_risk(avg)})
        return pd.DataFrame(rows)
    def _ensure_dir(p:str):
        if not os.path.isdir(p): os.makedirs(p, exist_ok=True)
    def save_report_and_picks(theme_rows, theme_stocks_map, out_dir="reports", top_n=5, prefix: Optional[str]=None):
        ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S"); tag=(prefix+"_") if prefix else ""; _ensure_dir(out_dir)
        rep = make_theme_report(theme_rows, theme_stocks_map); picks = pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n)
        report_csv=os.path.join(out_dir,f"{tag}theme_report_{ts}.csv"); report_json=os.path.join(out_dir,f"{tag}theme_report_{ts}.json")
        picks_csv=os.path.join(out_dir,f"{tag}promising_picks_{ts}.csv"); picks_json=os.path.join(out_dir,f"{tag}promising_picks_{ts}.json")
        rep.to_csv(report_csv,index=False,encoding="utf-8-sig"); picks.to_csv(picks_csv,index=False,encoding="utf-8-sig")
        import json as _json
        with open(report_json,"w",encoding="utf-8") as f: _json.dump(rep.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
        with open(picks_json,"w",encoding="utf-8") as f: _json.dump(picks.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
        return {"report_csv":report_csv,"report_json":report_json,"picks_csv":picks_csv,"picks_json":picks_json}

# analyzer
try:
    from modules.analyzer import init_db, analyze_stock, load_recent  # type: ignore
except Exception:
    def init_db(): return True
    def analyze_stock(name: str, ticker: str):
        return (f"{name}({ticker}) 분석 요약 – 폴백", {"name":name, "ticker":ticker, "score":80})
    def load_recent(limit: int = 10) -> pd.DataFrame:
        return pd.DataFrame([
            {"시간": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "종목명":"삼성전자", "티커":"005930.KS", "요약":"폴백 기록"}
        ])

# ==========================================================
# 3) 페이지 설정/공통 UI
# ==========================================================
st.set_page_config(page_title="AI 뉴스리포트 – 자동 테마·시세 예측", layout="wide")
st.markdown(inject_base_css(), unsafe_allow_html=True)
st.markdown(render_quick_menu(), unsafe_allow_html=True)
st.markdown("<div class='compact'>", unsafe_allow_html=True)

# 헤더 & 리프레시
c1, c2 = st.columns([5,1])
with c1:
    st.markdown("<h2 id='sec-ticker'>🧠 AI 뉴스리포트 – 실시간 지수 티커바</h2>", unsafe_allow_html=True)
    st.caption(f"업데이트: {datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S (KST)')}")
with c2:
    if st.button("🔄 새로고침", use_container_width=True):
        try:
            st.cache_data.clear()  # type: ignore[attr-defined]
        except Exception:
            pass
        try:
            st.rerun()
        except Exception:
            pass

# ==========================================================
# 4) 티커바
# ==========================================================
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

# ==========================================================
# 5) 최신 뉴스
# ==========================================================
st.markdown("<h2 id='sec-news'>📰 최신 뉴스 요약</h2>", unsafe_allow_html=True)
col1, col2 = st.columns([2,1])
with col1:
    cat = st.selectbox("📂 카테고리", list(CATEGORIES.keys()))
with col2:
    page = st.number_input("페이지", min_value=1, value=1, step=1)

try:
    @st.cache_data(ttl=300)  # type: ignore[misc]
    def _fetch_category_news_cached(_cat: str, _days: int, _max: int):
        return fetch_category_news(_cat, days=_days, max_items=_max)
except Exception:
    def _fetch_category_news_cached(_cat: str, _days: int, _max: int):
        return fetch_category_news(_cat, days=_days, max_items=_max)

news_all = _fetch_category_news_cached(cat, 3, 100)
page_size = 10
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

# ==========================================================
# 6) 뉴스 기반 테마 + 자동 키워드 추천
# ==========================================================
st.markdown("<h2 id='sec-themes'>🔥 뉴스 기반 테마 요약</h2>", unsafe_allow_html=True)
st.caption("뉴스 본문/제목에서 키워드를 추출하고, 자동 테마 감지→추천까지 한번에 구성합니다.")

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

# ---- 자동 키워드 추천 ----
try:
    titles_for_kw = [n.get("title", "") for n in (all_news or [])]
    auto_keywords = extract_keywords(titles_for_kw, topn=15) if titles_for_kw else []
except Exception:
    auto_keywords = []

if auto_keywords:
    st.markdown("**🧩 자동 키워드(Top 15)**: " + " ".join([f"<span class='chip'>{k}</span>" for k in auto_keywords]), unsafe_allow_html=True)

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

# ==========================================================
# 7) AI 유망 종목 Top5 (테마다 1종목)
# ==========================================================
st.markdown("<h2 id='sec-top5'>🚀 오늘의 AI 유망 종목 Top5 (테마다 1종목)</h2>", unsafe_allow_html=True)
try:
    @st.cache_data(ttl=120)  # type: ignore[misc]
    def _pick_promising_once(_theme_rows, _theme_stocks, _top_n):
        return pick_promising_by_theme_once(_theme_rows, _theme_stocks, top_n=_top_n)
except Exception:
    def _pick_promising_once(_theme_rows, _theme_stocks, _top_n):
        return pick_promising_by_theme_once(_theme_rows, _theme_stOCKS, top_n=_top_n)  # type: ignore[name-defined]

rec_df = _pick_promising_once(theme_rows, THEME_STOCKS, 5) if theme_rows else pd.DataFrame()
if rec_df is None or rec_df.empty:
    st.info("추천할 종목이 없습니다. (유동성/이상치 필터로 제외됐을 수 있어요)")
else:
    st.dataframe(rec_df, use_container_width=True, hide_index=True)

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

# ==========================================================
# 8) 저장 기능 (버튼 + 자동) + 원클릭
# ==========================================================

def _do_save(prefix: str = "dashboard") -> Dict[str, str]:
    if not theme_rows:
        raise RuntimeError("저장할 테마 데이터가 없습니다.")
    paths = save_report_and_picks(theme_rows, THEME_STOCKS, out_dir="reports", top_n=5, prefix=prefix)
    return paths

col_auto1, col_auto2 = st.columns([1,1])
with col_auto1:
    if st.button("🪄 한번에 분석+추천+저장", use_container_width=True):
        if not theme_rows:
            st.warning("테마 신호가 약해 저장을 건너뜁니다.")
        else:
            try:
                st.success("분석 및 추천 완료! 아래에 저장된 파일 경로가 표시됩니다.")
                paths = _do_save(prefix="oneclick")
                st.json(paths)
            except Exception as e:
                st.error(f"원클릭 처리 실패: {e}")
with col_auto2:
    st.caption("※ 뉴스→테마 감지→유망종목 추천→CSV/JSON 저장까지 한 번에 실행")

st.divider()

# 수동 저장 버튼
if st.button("💾 리포트 & 유망종목 저장", use_container_width=True):
    try:
        paths = _do_save(prefix="dashboard")
        st.success("저장 완료! 아래 경로를 확인하세요.")
        st.json(paths)
    except Exception as e:
        st.error(f"저장 실패: {e}")

# 세션당 1회 자동 저장
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

st.markdown("</div>", unsafe_allow_html=True)

# ==========================================================
# 9) 종목 분석 & 기록
# ==========================================================
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

# ==========================================================
# 10) 간단 셀프 테스트 (Streamlit 미설치/모듈 부재 환경 검증)
# ==========================================================

def run_self_tests() -> None:
    # 1) 티커 아이템
    its = build_ticker_items(); assert isinstance(its, list) and len(its)>=1
    # 2) 뉴스/테마 파이프라인
    cats = list(CATEGORIES.keys()); assert len(cats)>=1
    news = fetch_category_news(cats[0], days=3, max_items=5); assert isinstance(news, list) and len(news)>=1
    alln = fetch_all_news(days=3, per_cat=5); th = detect_themes(alln); assert isinstance(th, list)
    # 3) 추천 TopN 스키마
    df = pick_promising_by_theme_once(th, THEME_STOCKS, top_n=5); assert isinstance(df, pd.DataFrame)
    if not df.empty:
        for col in ["종목명","티커","테마","등락률(%)","뉴스빈도","AI점수"]:
            assert col in df.columns
    # 4) 저장 기능
    paths = save_report_and_picks(th, THEME_STOCKS, out_dir="reports_test", top_n=3, prefix="unittest")
    for k in ["report_csv","report_json","picks_csv","picks_json"]:
        assert os.path.isfile(paths[k])

if __name__ == "__main__":
    run_self_tests()
    print("[app.py] ✅ Self-tests passed. STREAMLIT:", STREAMLIT_AVAILABLE)
