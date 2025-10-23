# -*- coding: utf-8 -*-
import streamlit as st
import json, os
import pandas as pd
from datetime import datetime, timezone, timedelta

# -------------------------------
# 기본 설정
# -------------------------------
st.set_page_config(page_title="AI 뉴스리포트 대시보드", layout="wide")
st.title("🧠 AI 뉴스리포트 종합 대시보드 (자동 업데이트)")

# -------------------------------
# 유틸리티 함수
# -------------------------------
def safe_load_json(path, default):
    """JSON 안전 로드 (파일 없거나 포맷 깨져도 기본값 반환)"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# -------------------------------
# ① 시장 요약 (지수 / 환율 / 원자재)
# -------------------------------
st.header("📊 오늘의 시장 요약")

market = safe_load_json("data/market_today.json", {})
info = market if isinstance(market, dict) else {}

def format_value(v):
    if v is None: return "-"
    try: return f"{float(v):,.2f}"
    except: return str(v)

cols = st.columns(3)
cols[0].metric("KOSPI", format_value(info.get("kospi", {}).get("value")),
               f"{info.get('kospi', {}).get('change_pct', '-')}")
cols[1].metric("KOSDAQ", format_value(info.get("kosdaq", {}).get("value")),
               f"{info.get('kosdaq', {}).get('change_pct', '-')}")
cols[2].metric("환율(USD/KRW)", format_value(info.get("usdkrw", {}).get("value")),
               f"{info.get('usdkrw', {}).get('change_pct', '-')}")
st.caption(f"업데이트 시간: {info.get('updated_at','-')}")

st.markdown("---")


# -------------------------------
# ② 최신 경제·정책·산업·리포트 뉴스 TOP10
# -------------------------------
st.subheader("📰 최신 경제·정책·산업·리포트 뉴스 TOP 10")

raw = safe_load_json("data/headlines_top10.json", {})
items = raw.get("items", raw if isinstance(raw, list) else [])

safe_items = []
for x in items:
    if isinstance(x, dict):
        title = x.get("title") or x.get("headline") or x.get("tit") or ""
        link = x.get("link") or x.get("url") or None
    elif isinstance(x, (list, tuple)):
        title = str(x[0])
        link = x[1] if len(x) > 1 else None
    else:
        title = str(x)
        link = None
    if title.strip():
        safe_items.append({"title": title.strip(), "link": link})

if not safe_items:
    st.info("헤드라인 없음")
else:
    for i, n in enumerate(safe_items[:10], 1):
        if n.get("link"):
            st.markdown(f"{i}. [{n['title']}]({n['link']})")
        else:
            st.markdown(f"{i}. {n['title']}")

st.markdown("---")


# -------------------------------
# ③ 뉴스 기반 TOP 테마 (5개)
# -------------------------------
st.subheader("🔥 뉴스 기반 TOP 테마")

theme_raw = safe_load_json("data/theme_top5.json", {})
theme_list = theme_raw.get("themes", theme_raw if isinstance(theme_raw, list) else [])

rows = []
for t in theme_list:
    if isinstance(t, dict):
        theme = t.get("theme") or t.get("name") or ""
        score = t.get("score", t.get("count", 0))
    else:
        theme = str(t)
        score = 0
    if theme:
        try:
            score = float(score)
        except:
            score = 0.0
        rows.append({"theme": theme, "score": score})

if rows:
    df_theme = pd.DataFrame(rows).sort_values("score", ascending=False).head(5)
    st.bar_chart(df_theme.set_index("theme"))
else:
    st.info("테마 데이터 없음")

st.markdown("---")


# -------------------------------
# ④ 전체 테마 요약 테이블
# -------------------------------
st.subheader("📊 전체 테마 집계 (감쇠 점수 포함)")

theme2_raw = safe_load_json("data/theme_secondary5.json", {})
theme2_list = theme2_raw.get("themes", theme2_raw if isinstance(theme2_raw, list) else [])
df_theme2 = pd.DataFrame(theme2_list) if theme2_list else pd.DataFrame(columns=["theme","count","score"])
st.dataframe(df_theme2)


# -------------------------------
# ⑤ 월간 키워드맵
# -------------------------------
st.subheader("🌍 월간 키워드맵 (최근 30일)")

kw_raw = safe_load_json("data/keyword_map_month.json", {})
kw_list = kw_raw.get("keywords", kw_raw if isinstance(kw_raw, list) else [])

kw_rows = []
for k in kw_list:
    if isinstance(k, dict):
        word = k.get("keyword") or k.get("word") or ""
        cnt = k.get("count", 0)
    else:
        word = str(k)
        cnt = 0
    if word:
        try:
            cnt = int(cnt)
        except:
            cnt = 0
        kw_rows.append({"keyword": word, "count": cnt})

if kw_rows:
    df_kw = pd.DataFrame(kw_rows).sort_values("count", ascending=False).head(30)
    st.bar_chart(df_kw.set_index("keyword"))
else:
    st.info("키워드 없음")

st.markdown("---")


# -------------------------------
# ⑥ 신규 테마 감지 (바이그램 등)
# -------------------------------
st.subheader("🧪 신규 테마 감지 (바이그램)")

if os.path.exists("data/new_themes.json"):
    new_themes = safe_load_json("data/new_themes.json", [])
    if new_themes:
        for t in new_themes:
            st.markdown(f"- {t}")
    else:
        st.info("신규 테마 없음")
else:
    st.info("데이터 없음")

st.markdown("---")

st.success("✅ 대시보드 로딩 완료 (모든 오류 방지 적용됨)")
