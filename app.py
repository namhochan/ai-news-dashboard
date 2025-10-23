# app.py
# AI 뉴스리포트 종합 대시보드 (지수/환율/원자재 런타임 폴백 포함)
# - data/market_today.json이 없어도 yfinance로 즉시 값을 가져와 표시
# - 다른 데이터 파일이 없어도 빈 상태로 안전하게 렌더링

import os
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd

# ====== UI 기본 설정 ======
st.set_page_config(page_title="AI 뉴스리포트 종합 대시보드", layout="wide")
st.markdown("# 🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")
st.caption("업데이트 시간: " + datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S (KST)"))

# ====== 공용 유틸 ======
KST = timezone(timedelta(hours=9))

def load_json_safe(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def kst_now_iso():
    return datetime.now(KST).isoformat()

# ====== (핵심) 지수/환율/원자재 런타임 폴백 ======
# market_today.json이 비어있거나 오래되면, 여기서 yfinance로 채워 넣음
import yfinance as yf

FALLBACK_TICKERS = {
    "KOSPI":  "^KS11",
    # KOSDAQ은 지역/시점에 따라 공백이 나올 수 있습니다. ^KQ11을 우선 사용,
    # 필요시 ^KOSDAQ 으로 교체 테스트 가능
    "KOSDAQ": "^KQ11",
    "USDKRW":"KRW=X",
    "WTI":    "CL=F",
    "Gold":   "GC=F",
    "Copper": "HG=F",
}

def _last_two_prices(ticker: str):
    """최근 10영업일에서 종가 2개 가져오기"""
    try:
        df = yf.download(ticker, period="10d", interval="1d", progress=False)
        closes = df["Close"].dropna().tail(2).tolist()
        if len(closes) == 1:
            return float(closes[0]), None
        if len(closes) >= 2:
            return float(closes[-1]), float(closes[-2])
    except Exception:
        pass
    return None, None

def _pct_change(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    try:
        if prev in (None, 0) or cur is None:
            return None
        return round((cur - prev) / prev * 100.0, 2)
    except Exception:
        return None

def _is_stale(asof_iso: Optional[str]) -> bool:
    try:
        if not asof_iso:
            return True
        asof = datetime.fromisoformat(asof_iso)
        age = datetime.now(KST) - asof
        return age.total_seconds() > 6 * 3600  # 6시간 이상이면 오래된 것으로 간주
    except Exception:
        return True

def load_market_with_fallback(local_json_path: str) -> Dict[str, Any]:
    """1) 로컬 JSON을 읽고, 2) 값이 없거나 오래되면 yfinance로 채워서 반환.
       3) 채워졌으면 파일도 갱신(캐시)."""
    data = load_json_safe(local_json_path, default={})

    updated = False
    for name, y_ticker in FALLBACK_TICKERS.items():
        entry = data.get(name, {})
        val = entry.get("value")
        asof = entry.get("asof")

        if val is None or _is_stale(asof):
            cur, prev = _last_two_prices(y_ticker)
            chg = _pct_change(cur, prev) if (cur is not None and prev is not None) else None
            data[name] = {
                "value": None if cur is None else round(cur, 2),
                "prev":  None if prev is None else round(prev, 2) if prev is not None else None,
                "change_pct": chg,
                "ticker": y_ticker,
                "asof": kst_now_iso()
            }
            updated = True

    if updated:
        try:
            os.makedirs(os.path.dirname(local_json_path), exist_ok=True)
            with open(local_json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            # 파일 캐시 저장 실패는 무시 (화면 렌더링엔 영향 없음)
            pass
    return data

# ====== 데이터 로딩 ======
market = load_market_with_fallback("data/market_today.json")
headlines: List[Dict[str, str]] = load_json_safe("data/headlines_top10.json", default=[])
themes_table: List[Dict[str, Any]] = load_json_safe("data/themes_scored.json", default=[])  # 선택
monthly_keywords: List[Dict[str, Any]] = load_json_safe("data/keywords_monthly.json", default=[])  # 선택

# ====== 컴포넌트 렌더링 ======
def render_market_cards(market_data: Dict[str, Any]):
    st.subheader("📊 오늘의 시장 요약")
    col1, col2, col3 = st.columns(3)
    col4, col5, col6 = st.columns(3)

    def _card(col, title, key):
        d = market_data.get(key, {})
        val = d.get("value")
        chg = d.get("change_pct")
        # 숫자나 포맷이 없으면 대시로 표시
        if val is None:
            col.metric(title, value="-", delta="None")
        else:
            # 환율은 소수점 2, 원자재도 2, 지수는 2로 통일
            vtxt = f"{val:,.2f}"
            if chg is None:
                col.metric(title, value=vtxt, delta="None")
            else:
                # 증가/감소 화살표는 metric에서 자동 적용
                col.metric(title, value=vtxt, delta=f"{chg:+.2f}%")

    _card(col1, "KOSPI", "KOSPI")
    _card(col2, "KOSDAQ", "KOSDAQ")
    _card(col3, "환율(USD/KRW)", "USDKRW")

    _card(col4, "WTI", "WTI")
    _card(col5, "Gold", "Gold")
    _card(col6, "Copper", "Copper")

def render_headlines(items: List[Dict[str, str]]):
    st.subheader("📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")
    if not items:
        st.info("헤드라인 없음")
        return
    for i, n in enumerate(items, start=1):
        title = n.get("title", "(제목 없음)")
        link = n.get("link", "#")
        st.markdown(f"{i}. [{title}]({link})")

def render_theme_chart(themes: List[Dict[str, Any]]):
    st.subheader("🔥 뉴스 기반 TOP 테마")
    if not themes:
        st.info("테마 데이터 없음")
        return
    try:
        df = pd.DataFrame(themes)  # columns: theme, count, score, sample_link, stocks(optional)
        # 시각화용 단순 bar
        st.bar_chart(df.set_index("theme")["count"])
        with st.expander("전체 테마 집계 (감쇠 점수 포함)"):
            st.dataframe(df)
    except Exception as e:
        st.warning(f"테마 시각화 중 오류: {e}")

def render_monthly_keywords(keywords: List[Dict[str, Any]]):
    st.subheader("🌐 월간 키워드맵 (최근 30일)")
    if not keywords:
        st.info("키워드 없음")
        return
    try:
        df = pd.DataFrame(keywords)  # columns: keyword, count
        st.bar_chart(df.set_index("keyword")["count"])
    except Exception as e:
        st.warning(f"키워드 시각화 중 오류: {e}")

# ====== 페이지 출력 ======
render_market_cards(market)
st.divider()
render_headlines(headlines)
st.divider()
render_theme_chart(themes_table)
st.divider()
render_monthly_keywords(monthly_keywords)

st.success("대시보드 로딩 완료 (지수 폴백 활성화)")
