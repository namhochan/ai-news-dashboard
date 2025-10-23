# app.py — AI 뉴스리포트 종합 대시보드 (대표 종목/전뉴스 2건 포함)
# ------------------------------------------------------------------
# 기대 파일 구조(자동 파이프라인이 주기적으로 생성/갱신):
# data/
#   headlines_top10.json       -> {"items":[{"title","link","published"},...]}
#   news_100.json              -> {"items":[...]}
#   theme_top5.json            -> {"themes":[{"theme","count","score","rep_stocks","sample_link"},...]}
#   theme_secondary5.json      -> {"themes":[{"theme","count","score","sample_link"},...]}
#   keyword_map_month.json     -> {"keywords":[{"keyword","count"},...]}
#   new_themes.json            -> ["신규 테마1", "신규 테마2", ...]
#
# 이 파일만 교체하면 화면에 대표 종목/전뉴스 2건까지 표시됩니다.

from __future__ import annotations
import os, json, time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
import feedparser

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="AI 뉴스리포트 종합 대시보드",
    layout="wide",
)

KST = timezone(timedelta(hours=9))

def kst_now_str() -> str:
    try:
        return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S (KST)")
    except Exception:
        return "-"

def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def to_list_of_stocks(rep_field) -> List[str]:
    """rep_stocks가 문자열/리스트 어떤 형태로 와도 안전하게 리스트로 변환"""
    if rep_field is None:
        return []
    if isinstance(rep_field, list):
        # 안에 [name] 혹은 [name,code] 형태도 올 수 있으니 첫 항목만 문자열로 표시
        out = []
        for x in rep_field:
            if isinstance(x, list) or isinstance(x, tuple):
                if x:
                    out.append(str(x[0]))
            else:
                out.append(str(x))
        return [s.strip() for s in out if s and s.strip()]
    if isinstance(rep_field, str):
        return [s.strip() for s in rep_field.split(",") if s.strip()]
    return []

def badge_delta(v: float | None) -> str:
    """증감 화살표 뱃지 HTML (값이 None이면 '--')"""
    if v is None:
        return "<span style='opacity:0.6'>—</span>"
    if v > 0:
        return f"<span style='color:#21c55d'>↑ {v:.2f}%</span>"
    if v < 0:
        return f"<span style='color:#ef4444'>↓ {abs(v):.2f}%</span>"
    return "<span>0.00%</span>"

def fetch_two_news(query: str, lang: str = "ko", gl: str = "KR") -> List[Dict[str, str]]:
    """
    구글뉴스 RSS에서 검색어 기준 최신 2건만 가져오기.
    Streamlit Cloud에서 외부 호출 허용.
    """
    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl={lang}&gl={gl}&ceid={gl}:{lang}"
        feed = feedparser.parse(url)
        out = []
        for e in feed.entries[:2]:
            out.append({"title": e.title, "link": getattr(e, "link", "")})
        return out
    except Exception:
        return []

# -----------------------------
# 헤더
# -----------------------------
st.markdown("# 🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")
st.caption(f"업데이트 시간: {kst_now_str()}")
# -----------------------------
# 오늘의 시장 요약 (yfinance → JSON → 표시)
# -----------------------------
st.markdown("## 📊 오늘의 시장 요약")

def read_market():
    path = "data/market_today.json"
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def badge_delta(v):
    if v is None:
        return "<span style='opacity:0.6'>—</span>"
    if v > 0:
        return f"<span style='color:#21c55d'>↑ {v:.2f}%</span>"
    if v < 0:
        return f"<span style='color:#ef4444'>↓ {abs(v):.2f}%</span>"
    return "<span>0.00%</span>"

mkt = read_market()

def metric_card(label, key):
    d = mkt.get(key, {})
    val = d.get("value", None)
    chg = d.get("change_pct", None)
    st.caption(label)
    st.markdown(f"### {val if val is not None else '—'}")
    st.markdown(badge_delta(chg), unsafe_allow_html=True)

c1, c2, c3 = st.columns(3)
with c1:
    metric_card("KOSPI", "KOSPI")
with c2:
    metric_card("KOSDAQ", "KOSDAQ")
with c3:
    metric_card("환율(USD/KRW)", "USDKRW")

c4, c5, c6 = st.columns(3)
with c4:
    metric_card("WTI", "WTI")
with c5:
    metric_card("Gold", "Gold")
with c6:
    metric_card("Copper", "Copper")

st.divider()

# -----------------------------
# 최신 헤드라인 Top 10
# -----------------------------
st.markdown("## 📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")
top10 = load_json("data/headlines_top10.json", {"items": []}).get("items", [])
if not top10:
    st.info("헤드라인 없음")
else:
    for i, n in enumerate(top10, 1):
        title = n.get("title", "제목 없음")
        link = n.get("link", "")
        if link:
            st.markdown(f"{i}. [{title}]({link})")
        else:
            st.markdown(f"{i}. {title}")

st.divider()

# -----------------------------
# 🔥 뉴스 기반 TOP 테마 (대표 종목/링크 포함)
# -----------------------------
st.markdown("## 🔥 뉴스 기반 TOP 테마")
top5 = load_json("data/theme_top5.json", {"themes": []}).get("themes", [])

if not top5:
    st.info("테마 데이터 없음")
else:
    # 막대차트
    try:
        df_bar = pd.DataFrame(
            [{"theme": r.get("theme", ""), "score": r.get("score", r.get("count", 0))} for r in top5]
        ).set_index("theme")
        st.bar_chart(df_bar)
    except Exception:
        pass

    # 카드 상세
    for r in top5:
        theme = r.get("theme", "")
        score = r.get("score", r.get("count", 0))
        sample_link = r.get("sample_link", "")
        stocks = to_list_of_stocks(r.get("rep_stocks"))

        with st.container(border=True):
            st.markdown(f"### {theme} · 점수 **{score}**")
            if stocks:
                st.caption("대표 종목")
                st.write(" | ".join(stocks))

                # 종목별 전뉴스 2건 (접기)
                with st.expander("종목별 전뉴스(최신 2건) 보기"):
                    for s in stocks:
                        news2 = fetch_two_news(s)
                        st.markdown(f"- **{s}**")
                        if not news2:
                            st.write("  · 뉴스 없음")
                        else:
                            for n in news2:
                                st.markdown(f"  · [{n['title']}]({n['link']})")
            else:
                st.caption("대표 종목 정보 없음")

            if sample_link:
                st.markdown(f"[관련 뉴스 보기]({sample_link})")

st.divider()

# -----------------------------
# 📊 전체 테마 집계 (감쇠 점수 포함)
# -----------------------------
st.markdown("## 📊 전체 테마 집계 (감쇠 점수 포함)")
secondary = load_json("data/theme_secondary5.json", {"themes": []}).get("themes", [])
if not secondary:
    st.info("데이터 없음")
else:
    df_sec = pd.DataFrame(
        [{
            "theme": r.get("theme", ""),
            "count": r.get("count", 0),
            "score": r.get("score", 0),
            "sample_link": r.get("sample_link", "")
        } for r in secondary]
    )
    st.dataframe(df_sec, use_container_width=True, hide_index=True)

    with st.expander("테마별 샘플 뉴스 링크"):
        for r in secondary[:30]:
            tl = r.get("theme", "")
            sl = r.get("sample_link", "")
            st.markdown(f"- **{tl}** — {('[링크]('+sl+')') if sl else ''}")

st.divider()

# -----------------------------
# 🌍 월간 키워드맵 (최근 30일)
# -----------------------------
st.markdown("## 🌍 월간 키워드맵 (최근 30일)")
kw = load_json("data/keyword_map_month.json", {"keywords": []}).get("keywords", [])
if not kw:
    st.info("키워드 없음")
else:
    try:
        df_kw = pd.DataFrame(kw)
        df_kw = df_kw.sort_values("count", ascending=False).head(30)
        df_kw = df_kw.set_index("keyword")
        st.bar_chart(df_kw)
    except Exception:
        st.info("키워드 시각화 실패(데이터 형식 확인 필요)")

st.divider()

# -----------------------------
# 🧪 신규 테마 감지 (바이그램)
# -----------------------------
st.markdown("## 🧪 신규 테마 감지 (바이그램)")
new_themes = load_json("data/new_themes.json", [])
if not new_themes:
    st.info("데이터 없음")
else:
    st.write("\n".join([f"- {t}" for t in new_themes]))

# -----------------------------
# 푸터
# -----------------------------
st.success("대시보드 로딩 완료 (에러 방지 처리 적용)")
