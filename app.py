# app.py
# AI 뉴스리포트 종합 대시보드 (강화판)
# - 지수/환율/원자재: 런타임 yfinance 폴백 + KOSDAQ 다중 티커 시도
# - 모든 섹션 방어: 파일 없어도/필드 형태 달라도 크래시 방지
# - 표시는 안전하게 "-", "None"으로 처리

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union

import streamlit as st
import pandas as pd

# ===== UI =====
st.set_page_config(page_title="AI 뉴스리포트 종합 대시보드", layout="wide")
KST = timezone(timedelta(hours=9))
st.markdown("# 🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")
st.caption("업데이트 시간: " + datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)"))

# ===== 공용 유틸 =====
def load_json_safe(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def kst_now_iso() -> str:
    return datetime.now(KST).isoformat()

def to_float_safe(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

# ===== yfinance 폴백 (지수/환율/원자재) =====
import yfinance as yf

# KOSDAQ은 지역/프로바이더 따라 다릅니다. 후보를 차례로 시도합니다.
KOSDAQ_CANDIDATES = ["^KQ11", "^KOSDAQ", "KQ11"]

FALLBACK_TICKERS = {
    "KOSPI":  ["^KS11"],
    "KOSDAQ": KOSDAQ_CANDIDATES,
    "USDKRW": ["KRW=X"],
    "WTI":    ["CL=F"],
    "Gold":   ["GC=F"],
    "Copper": ["HG=F"],
}

def _last_two_prices_try(ticker: str) -> Tuple[Optional[float], Optional[float]]:
    try:
        df = yf.download(ticker, period="10d", interval="1d", progress=False)
        closes = df.get("Close")
        if closes is None:
            return None, None
        vals = closes.dropna().tail(2).tolist()
        if len(vals) == 1:
            return float(vals[0]), None
        if len(vals) >= 2:
            return float(vals[-1]), float(vals[-2])
    except Exception:
        pass
    return None, None

def last_two_prices_any(tickers: List[str]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    for t in tickers:
        cur, prev = _last_two_prices_try(t)
        if cur is not None:
            return cur, prev, t
    return None, None, None

def pct_change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    try:
        if prev in (None, 0) or cur is None:
            return None
        return round((cur - prev) / prev * 100.0, 2)
    except Exception:
        return None

def is_stale(asof_iso: Optional[str], max_hours: int = 6) -> bool:
    try:
        if not asof_iso:
            return True
        asof = datetime.fromisoformat(asof_iso)
        age = datetime.now(KST) - asof
        return age.total_seconds() > max_hours * 3600
    except Exception:
        return True

def load_market_with_fallback(local_json_path: str) -> Dict[str, Any]:
    """로컬 JSON을 우선 읽고, 비었거나 오래됐으면 yfinance로 채움(파일도 갱신)."""
    data: Dict[str, Any] = load_json_safe(local_json_path, default={})
    updated = False

    for name, candidates in FALLBACK_TICKERS.items():
        entry = data.get(name, {})
        val = to_float_safe(entry.get("value"))
        asof = entry.get("asof")

        if val is None or is_stale(asof):
            cur, prev, used = last_two_prices_any(candidates)
            chg = pct_change(cur, prev)
            data[name] = {
                "value": None if cur is None else round(cur, 2),
                "prev":  None if prev is None else round(prev, 2),
                "change_pct": chg,
                "ticker": used,
                "asof": kst_now_iso()
            }
            updated = True

    if updated:
        try:
            os.makedirs(os.path.dirname(local_json_path), exist_ok=True)
            with open(local_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return data

# ===== 데이터 로드 =====
market = load_market_with_fallback("data/market_today.json")

# headlines_top10.json은 항목이 dict 또는 문자열일 수 있어 방어 처리
raw_headlines: Any = load_json_safe("data/headlines_top10.json", default=[])
# themes_scored.json (선택)
raw_themes: Any = load_json_safe("data/themes_scored.json", default=[])
# keywords_monthly.json (선택)
raw_keywords: Any = load_json_safe("data/keywords_monthly.json", default=[])

# ===== 렌더링 =====
def render_market_cards(market_data: Dict[str, Any]):
    st.subheader("📊 오늘의 시장 요약")
    col1, col2, col3 = st.columns(3)
    col4, col5, col6 = st.columns(3)

    def metric_block(col, title, key):
        d = market_data.get(key, {})
        val = to_float_safe(d.get("value"))
        chg = to_float_safe(d.get("change_pct"))
        if val is None:
            col.metric(title, value="-", delta="None")
        else:
            vtxt = f"{val:,.2f}"
            col.metric(title, value=vtxt, delta="None" if chg is None else f"{chg:+.2f}%")

    metric_block(col1, "KOSPI", "KOSPI")
    metric_block(col2, "KOSDAQ", "KOSDAQ")
    metric_block(col3, "환율(USD/KRW)", "USDKRW")
    metric_block(col4, "WTI", "WTI")
    metric_block(col5, "Gold", "Gold")
    metric_block(col6, "Copper", "Copper")

def normalize_headlines(items: Any) -> List[Dict[str, str]]:
    """각 항목이 dict 또는 문자열이어도 title/link 필드를 만들어 반환."""
    norm: List[Dict[str, str]] = []
    if not isinstance(items, list):
        return norm
    for x in items:
        if isinstance(x, dict):
            title = str(x.get("title") or x.get("headline") or x.get("t") or "").strip()
            link = str(x.get("link") or x.get("url") or "#").strip()
        elif isinstance(x, str):
            title, link = x.strip(), "#"
        else:
            title, link = "", "#"
        if title:
            norm.append({"title": title, "link": link})
    return norm

def render_headlines(items: Any):
    st.subheader("📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")
    rows = normalize_headlines(items)
    if not rows:
        st.info("헤드라인 없음")
        return
    for i, n in enumerate(rows, start=1):
        title = n.get("title", "(제목 없음)")
        link = n.get("link", "#") or "#"
        # 내부 markdown 안전 처리
        esc_title = title.replace("[", "［").replace("]", "］")
        st.markdown(f"{i}. [{esc_title}]({link})")

def normalize_themes(items: Any) -> pd.DataFrame:
    """theme/count/score/sample_link/rep_stocks(옵션)을 가진 DataFrame으로 변환."""
    if not isinstance(items, list) or not items:
        return pd.DataFrame(columns=["theme", "count", "score", "sample_link", "rep_stocks"])
    out = []
    for x in items:
        if not isinstance(x, dict):
            continue
        theme = str(x.get("theme") or x.get("name") or "").strip()
        count = to_float_safe(x.get("count")) or 0
        score = to_float_safe(x.get("score")) or count
        slink = str(x.get("sample_link") or x.get("link") or "")
        stocks = x.get("rep_stocks") or x.get("stocks") or []
        if isinstance(stocks, list):
            stocks_txt = " · ".join([str(s) for s in stocks])
        else:
            stocks_txt = str(stocks)
        if theme:
            out.append({"theme": theme, "count": count, "score": score, "sample_link": slink, "rep_stocks": stocks_txt})
    return pd.DataFrame(out)

def render_theme_chart(items: Any):
    st.subheader("🔥 뉴스 기반 TOP 테마")
    df = normalize_themes(items)
    if df.empty:
        st.info("테마 데이터 없음")
        return
    try:
        # count 기준 상위 10개만 표시
        top = df.sort_values(["score", "count"], ascending=False).head(10)
        st.bar_chart(top.set_index("theme")["count"])
        with st.expander("전체 테마 집계 (감쇠 점수 포함)"):
            st.dataframe(df.reset_index(drop=True), use_container_width=True)
    except Exception as e:
        st.warning(f"테마 시각화 중 오류: {e}")

def normalize_keywords(items: Any) -> pd.DataFrame:
    if not isinstance(items, list) or not items:
        return pd.DataFrame(columns=["keyword", "count"])
    out = []
    for x in items:
        if isinstance(x, dict):
            kw = str(x.get("keyword") or x.get("key") or "").strip()
            ct = to_float_safe(x.get("count")) or 0
        elif isinstance(x, (list, tuple)) and len(x) >= 2:
            kw = str(x[0]).strip()
            ct = to_float_safe(x[1]) or 0
        else:
            kw, ct = "", 0
        if kw:
            out.append({"keyword": kw, "count": ct})
    return pd.DataFrame(out)

def render_monthly_keywords(items: Any):
    st.subheader("🌐 월간 키워드맵 (최근 30일)")
    df = normalize_keywords(items)
    if df.empty:
        st.info("키워드 없음")
        return
    try:
        st.bar_chart(df.set_index("keyword")["count"])
    except Exception as e:
        st.warning(f"키워드 시각화 중 오류: {e}")

# ===== 출력 =====
render_market_cards(market)
st.divider()
render_headlines(raw_headlines)
st.divider()
render_theme_chart(raw_themes)
st.divider()
render_monthly_keywords(raw_keywords)

st.success("대시보드 로딩 완료 (강화 방어 로직 적용)")
