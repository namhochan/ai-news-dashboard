# modules/news.py – v3.7.1+R 구글 Relevance RSS 기반

from datetime import datetime, timedelta, timezone
from typing import Dict, List
import urllib.request, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

CATEGORIES = {
    "세계": ["세계 경제", "국제 무역", "미국 증시", "중국 경제"],
    "정책": ["정부 정책", "산업부", "예산", "금융위", "규제"],
    "경제": ["코스피", "코스닥", "금리", "물가", "환율", "GDP"],
    "산업": ["AI", "반도체", "배터리", "로봇", "자동차", "전력"],
}

def _fetch_google_news(keyword: str, days: int = 3, limit: int = 40) -> List[Dict[str, str]]:
    """Google News RSS (Relevance 기반)"""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(keyword)}&hl=ko&gl=KR&ceid=KR:ko&scoring=r"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        now = datetime.now(KST)
        items = []
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            desc = (it.findtext("description") or "").replace("<br>", " ")
            pub = it.findtext("pubDate") or ""
            try:
                t = parsedate_to_datetime(pub)
                if t.tzinfo is None:
                    t = t.replace(tzinfo=timezone.utc)
                t = t.astimezone(KST)
            except Exception:
                t = None
            if t and (now - t) > timedelta(days=days):
                continue
            items.append({
                "title": title,
                "link": link,
                "time": t.strftime("%Y-%m-%d %H:%M") if t else "-",
                "desc": desc,
            })
        return items[:limit]
    except Exception:
        return []

def fetch_category_news(cat: str, days: int = 3, per_kw: int = 25, max_total: int = 100):
    """카테고리별 키워드 순회 → 100건 병합"""
    seen, merged = set(), []
    for kw in CATEGORIES.get(cat, []):
        for it in _fetch_google_news(kw, days=days, limit=per_kw):
            key = it["title"]
            if key in seen: continue
            seen.add(key)
            merged.append(it)
    merged.sort(key=lambda x: x.get("time", ""), reverse=True)
    return merged[:max_total]

def fetch_all_news(days: int = 3) -> List[Dict[str, str]]:
    all_items = []
    for cat in CATEGORIES:
        all_items.extend(fetch_category_news(cat, days))
    return all_items

def detect_themes(news_list: List[Dict[str, str]]) -> Dict[str, int]:
    from collections import Counter
    import re
    themes = {
        "AI": ["ai","인공지능","챗GPT","엔비디아"],
        "반도체": ["반도체","hbm","칩","파운드리"],
        "로봇": ["로봇","amr","자율주행로봇"],
        "전력": ["전력","한전","송배전","스마트그리드"],
    }
    count = Counter()
    for n in news_list:
        text = (n["title"] + " " + n["desc"]).lower()
        for t, kws in themes.items():
            if any(k.lower() in text for k in kws):
                count[t] += 1
    return dict(count)
