# -*- coding: utf-8 -*-
"""
뉴스 크롤링(RSS) + 카테고리별 수집 + 테마 감지
- Google News RSS 기반 (User-Agent 지정)
- 최근 N일 필터, 최신순 정렬
- 테마 키워드 매칭으로 뉴스 건수 집계
"""

from datetime import datetime, timedelta
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
from typing import List, Dict

import pandas as pd
import streamlit as st
import feedparser
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")

# ---------------------------------------------------
# 카테고리 키워드 (app.py에서 선택지는 ["경제뉴스","산업뉴스","정책뉴스"])
# ---------------------------------------------------
CATEGORIES: Dict[str, List[str]] = {
    "경제뉴스": ["경제", "물가", "환율", "금리", "성장률", "무역", "경기", "수출입"],
    "산업뉴스": ["산업", "반도체", "AI", "배터리", "전력", "에너지", "자동차", "로봇", "데이터센터"],
    "정책뉴스": ["정책", "정부", "예산", "규제", "세금", "산업부", "금융위원회"],
}

# ---------------------------------------------------
# 테마 키워드 (간단 버전) — 필요시 관리자 모듈에서 확장 가능
# ---------------------------------------------------
THEME_KEYWORDS: Dict[str, List[str]] = {
    "AI":       ["ai", "인공지능", "챗봇", "엔비디아", "오픈ai", "생성형", "gpu"],
    "반도체":    ["반도체", "hbm", "칩", "램", "파운드리", "소부장"],
    "로봇":      ["로봇", "자율주행", "협동로봇", "amr", "로보틱스"],
    "이차전지":   ["배터리", "전고체", "양극재", "음극재", "lfp"],
    "에너지":    ["에너지", "정유", "전력", "태양광", "풍력", "가스", "발전", "전기요금"],
    "조선":      ["조선", "선박", "lng선", "해운", "수주"],
    "LNG":      ["lng", "액화천연가스", "가스공사", "터미널"],
    "원전":      ["원전", "smr", "원자력", "우라늄", "정비"],
    "바이오":    ["바이오", "제약", "신약", "임상", "시밀러"],
}

# ---------------------------------------------------
# 내부 유틸
# ---------------------------------------------------
def _clean_html(raw: str) -> str:
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days: int):
    now = datetime.now(KST)
    out = []
    for e in getattr(feed, "entries", []):
        t = None
        if getattr(e, "published_parsed", None):
            t = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            t = datetime(*e.updated_parsed[:6], tzinfo=KST)

        if t and (now - t) > timedelta(days=days):
            continue

        title = (getattr(e, "title", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
        desc = _clean_html(getattr(e, "summary", ""))

        out.append({
            "title": title,
            "link": link,
            "time": t.strftime("%Y-%m-%d %H:%M") if t else "-",
            "desc": desc,
        })
    # 최신순 정렬
    def _key(x):
        try:
            return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.min
    out.sort(key=_key, reverse=True)
    return out

# ---------------------------------------------------
# 공개 함수
# ---------------------------------------------------
@st.cache_data(ttl=900)
def fetch_google_news_by_keyword(keyword: str, days: int = 3, limit: int = 50):
    """Google News RSS를 키워드로 조회 (최근 N일, 최신순, 상한 limit)"""
    try:
        q = quote_plus(keyword)
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
        feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
        items = _parse_entries(feed, days)
        return items[:limit]
    except Exception:
        return []

@st.cache_data(ttl=900)
def fetch_category_news(cat: str, days: int = 3, max_items: int = 120):
    """카테고리의 여러 키워드를 합쳐 수집 후 중복 제거 + 최신순 + 상한"""
    seen, out = set(), []
    for kw in CATEGORIES.get(cat, []):
        for it in fetch_google_news_by_keyword(kw, days=days, limit=min(50, max_items)):
            k = (it["title"], it["link"])
            if k in seen:
                continue
            seen.add(k)
            out.append(it)

    # 최신순으로 잘려 나가도록 이미 _parse_entries에서 정렬하지만, 안전하게 재정렬
    def _key(x):
        try:
            return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.min
    out.sort(key=_key, reverse=True)
    return out[:max_items]

def detect_themes(news_list: List[dict]) -> pd.DataFrame:
    """
    기사 리스트에서 THEME_KEYWORDS와 매칭하여 테마별 건수 집계.
    반환: DataFrame(columns=["테마","뉴스건수","샘플 링크"])
    """
    counts = {t: 0 for t in THEME_KEYWORDS}
    sample = {t: "" for t in THEME_KEYWORDS}

    for n in news_list:
        text = ((n.get("title", "") or "") + " " + (n.get("desc", "") or "")).lower()
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                counts[theme] += 1
                if not sample[theme]:
                    sample[theme] = n.get("link", "")

    rows = [{"테마": t, "뉴스건수": c, "샘플 링크": sample[t]}
            for t, c in counts.items() if c > 0]
    df = pd.DataFrame(rows).sort_values("뉴스건수", ascending=False).reset_index(drop=True)
    return df
