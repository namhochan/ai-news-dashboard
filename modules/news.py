# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import time
from email.utils import parsedate_to_datetime

import requests
import feedparser
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))

CATEGORIES: Dict[str, List[str]] = {
    "경제뉴스": ["경제", "금리", "물가", "환율", "성장률", "무역"],
    "주식뉴스": ["코스피", "코스닥", "증시", "주가", "외국인 매수", "기관 매도"],
    "산업뉴스": ["반도체", "AI", "배터리", "자동차", "로봇", "수출입"],
    "정책뉴스": ["정책", "정부", "예산", "규제", "세금", "산업부"],
}

THEME_KEYWORDS: Dict[str, List[str]] = {
    "AI": ["ai","인공지능","챗봇","생성형","오픈ai","엔비디아","gpu","llm"],
    "반도체": ["반도체","hbm","칩","램","파운드리","소부장"],
    "로봇": ["로봇","협동로봇","amr","자율주행로봇","로보틱스"],
    "이차전지": ["2차전지","이차전지","배터리","전고체","양극재","음극재","lfp"],
    "에너지": ["에너지","정유","전력","가스","태양광","풍력"],
    "조선": ["조선","선박","수주","lng선","해운"],
    "LNG": ["lng","액화천연가스","가스공사","터미널"],
    "원전": ["원전","원자력","smr","우라늄"],
    "바이오": ["바이오","제약","신약","임상","항암"],
    "전력": ["전력","송배전","ESS","스마트그리드","전기요금"],
}

THEME_STOCKS: Dict[str, List[tuple]] = {
    "AI":[("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"),
          ("솔트룩스","304100.KQ"),("브레인즈컴퍼니","099390.KQ"),("한글과컴퓨터","030520.KS")],
    "반도체":[("SK하이닉스","000660.KS"),("DB하이텍","000990.KS"),("리노공업","058470.KQ"),
             ("원익IPS","240810.KQ"),("티씨케이","064760.KQ"),("에프에스티","036810.KQ")],
    "로봇":[("레인보우로보틱스","277810.KQ"),("유진로봇","056080.KQ"),("티로보틱스","117730.KQ"),
           ("로보스타","090360.KQ"),("스맥","099440.KQ")],
    "이차전지":[("LG에너지솔루션","373220.KS"),("포스코퓨처엠","003670.KS"),
              ("에코프로","086520.KQ"),("코스모신소재","005070.KQ"),("엘앤에프","066970.KQ")],
    "에너지":[("SK이노베이션","096770.KS"),("GS","078930.KS"),("S-Oil","010950.KS"),
            ("한화솔루션","009830.KS"),("OCI홀딩스","010060.KS")],
    "조선":[("HD한국조선해양","009540.KS"),("HD현대미포","010620.KS"),
           ("삼성중공업","010140.KS"),("한화오션","042660.KS")],
    "LNG":[("한국가스공사","036460.KS"),("지에스이","053050.KQ"),("대성에너지","117580.KQ"),("SK가스","018670.KS")],
    "원전":[("두산에너빌리티","034020.KS"),("우진","105840.KQ"),("한전KPS","051600.KS"),("보성파워텍","006910.KQ")],
    "바이오":[("셀트리온","068270.KS"),("에스티팜","237690.KQ"),("알테오젠","196170.KQ"),("메디톡스","086900.KQ")],
    "전력":[("한전KPS","051600.KS"),("LS ELECTRIC","010120.KS"),("효성중공업","298040.KS"),("대한전선","001440.KS")],
}

def _clean_html(raw: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_dt(s: str):
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST)
    except Exception:
        return None

def _http_get(url: str, timeout: int = 8, retries: int = 1) -> str:
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")
    last_err = None
    for i in range(retries+1):
        try:
            r = requests.get(url, headers={"User-Agent": ua}, timeout=timeout)
            if r.status_code == 200 and r.text:
                return r.text
        except Exception as e:
            last_err = e; time.sleep(0.25*(i+1))
    if last_err:
        raise last_err
    return ""

def _parse_entries(feed, days: int):
    now = datetime.now(KST)
    out = []
    for e in feed.entries:
        t = None
        if getattr(e, "published", None):
            t = _parse_dt(getattr(e, "published"))
        if t is None and getattr(e, "updated", None):
            t = _parse_dt(getattr(e, "updated"))
        if t and (now - t) > timedelta(days=days):
            continue
        title = (getattr(e, "title", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
        desc = _clean_html(getattr(e, "summary", ""))
        out.append({"title": title, "link": link, "time": t.strftime("%Y-%m-%d %H:%M") if t else "-", "desc": desc})
    return out

def fetch_google_news_by_keyword(keyword: str, days: int = 3, limit: int = 40):
    url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl=ko&gl=KR&ceid=KR%3Ako"
    xml = _http_get(url, timeout=8, retries=1)
    feed = feedparser.parse(xml)
    return _parse_entries(feed, days)[:max(1, int(limit))]

def fetch_category_news(cat: str, days: int = 3, max_items: int = 100):
    seen, merged = set(), []
    for kw in CATEGORIES.get(cat, []):
        try:
            for it in fetch_google_news_by_keyword(kw, days=days, limit=40):
                key = (it.get("title",""), it.get("link",""))
                if key in seen: continue
                seen.add(key); merged.append(it)
        except Exception:
            continue
    def _key(x):
        try:
            return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.min.replace(tzinfo=None)
    merged.sort(key=_key, reverse=True)
    return merged[:max(1, int(max_items))]

def fetch_all_news(days: int = 3, per_cat: int = 100):
    all_news = []
    for c in CATEGORIES.keys():
        try:
            all_news.extend(fetch_category_news(c, days=days, max_items=per_cat))
        except Exception:
            continue
    return all_news

def detect_themes(news_list):
    result, sample_link = {}, {}
    for n in news_list or []:
        text = f"{n.get('title','')} {n.get('desc','')}".lower()
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                result[theme] = result.get(theme, 0) + 1
                sample_link.setdefault(theme, n.get("link",""))
    rows = [{"theme": t, "count": c, "sample_link": sample_link.get(t,"")} for t, c in result.items() if c > 0]
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows
