# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus
import feedparser
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")

def _clean_html(raw: str) -> str:
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days: int):
    now = datetime.now(KST)
    out = []
    for e in feed.entries:
        t = None
        if getattr(e, "published_parsed", None):
            t = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            t = datetime(*e.updated_parsed[:6], tzinfo=KST)
        if t and (now - t) > timedelta(days=days):
            continue
        title = e.get("title", "").strip()
        link = e.get("link", "").strip()
        if link.startswith("./"): link = "https://news.google.com/" + link[2:]
        desc = _clean_html(e.get("summary", ""))
        out.append({"title": title, "link": link,
                    "time": t.strftime("%Y-%m-%d %H:%M") if t else "-",
                    "desc": desc})
    return out

def fetch_google_news(keyword: str, days: int = 3, limit: int = 40):
    q = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    return _parse_entries(feed, days)[:limit]
