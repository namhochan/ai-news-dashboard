# modules/news.py
import re
from urllib.parse import quote_plus
from datetime import datetime, timedelta
import feedparser
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd

def clean_html(raw): 
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days, now):
    out=[]
    for e in feed.entries:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = datetime(*e.published_parsed[:6])
        if pub and (now - pub) > timedelta(days=days):
            continue
        title = e.get("title","").strip()
        link  = e.get("link","").strip()
        if link.startswith("./"): link = "https://news.google.com/" + link[2:]
        desc  = clean_html(e.get("summary",""))
        out.append({"title":title, "link":link, "time": pub.strftime("%Y-%m-%d %H:%M") if pub else "-", "desc":desc})
    return out

def fetch_google_news_by_keyword(keyword, days=3, limit=40):
    now = datetime.utcnow()
    q = quote_plus(keyword)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent":"Mozilla/5.0"})
    return _parse_entries(feed, days, now)[:limit]

CATEGORIES = {
    "경제뉴스": ["경제","금리","물가","환율","성장률","무역"],
    "주식뉴스": ["코스피","코스닥","증시","주가","외국인 매수","기관 매도"],
    "산업뉴스": ["반도체","AI","배터리","자동차","로봇","수출입"],
    "정책뉴스": ["정책","정부","예산","규제","세금","산업부"],
}

def fetch_category_news(cat, days=3, max_items=100):
    seen, out = set(), []
    for kw in CATEGORIES.get(cat, []):
        try:
            for it in fetch_google_news_by_keyword(kw, days, 40):
                key = (it["title"], it["link"])
                if key in seen: 
                    continue
                seen.add(key); out.append(it)
        except Exception:
            continue
    def _key(x):
        try: return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except: return datetime.min
    return sorted(out, key=_key, reverse=True)[:max_items]

# ---- 테마 정의/매핑 ----
THEME_KEYWORDS = {
    "AI": ["ai","인공지능","챗봇","엔비디아","오픈ai","생성형"],
    "반도체": ["반도체","hbm","칩","램","파운드리","소부장"],
    "로봇": ["로봇","amr","협동로봇","자율주행로봇","로보틱스"],
    "이차전지": ["배터리","전고체","양극재","음극재","nickel","lithium"],
    "에너지": ["에너지","정유","전력","태양광","풍력","가스"],
    "조선": ["조선","선박","수주","lng선","해운"],
    "LNG": ["lng","액화","가스공사","터미널"],
    "원전": ["원전","원자력","smr","우라늄"],
    "바이오": ["바이오","제약","신약","임상"],
    "전력": ["전력","송전","배전","전력설비","한전","변전소","계통"],
}

THEME_STOCKS = {
    "AI":[("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"),
          ("솔트룩스","304100.KQ"),("브레인즈컴퍼니","099390.KQ"),("한글과컴퓨터","030520.KS")],
    "반도체":[("SK하이닉스","000660.KS"),("DB하이텍","000990.KS"),("리노공업","058470.KQ"),
          ("원익IPS","240810.KQ"),("티씨케이","064760.KQ"),("에프에스티","036810.KQ")],
    "로봇":[("레인보우로보틱스","277810.KQ"),("유진로봇","056080.KQ"),("티로보틱스","117730.KQ"),
          ("로보스타","090360.KQ"),("스맥","099440.KQ")],
    "이차전지":[("LG에너지솔루션","373220.KS"),("포스코퓨처엠","003670.KS"),
          ("에코프로","086520.KQ"),("코스모신소재","005070.KQ"),("엘앤에프","066970.KQ")],
    "에너지":[("한국전력","015760.KS"),("두산에너빌리티","034020.KS"),
          ("GS","078930.KS"),("한화솔루션","009830.KS"),("OCI홀딩스","010060.KS")],
    "조선":[("HD한국조선해양","009540.KS"),("HD현대미포","010620.KS"),
          ("삼성중공업","010140.KS"),("한화오션","042660.KS")],
    "LNG":[("한국가스공사","036460.KS"),("지에스이","053050.KQ"),("대성에너지","117580.KQ"),("SK가스","018670.KS")],
    "원전":[("두산에너빌리티","034020.KS"),("우진","105840.KQ"),("한전KPS","051600.KS"),("보성파워텍","006910.KQ")],
    "바이오":[("셀트리온","068270.KS"),("에스티팜","237690.KQ"),("알테오젠","196170.KQ"),("메디톡스","086900.KQ")],
    "전력":[("한전KPS","051600.KS"),("LS ELECTRIC","010120.KS"),("대한전선","001440.KS"),("HD현대일렉트릭","267260.KS")],
}

def detect_themes(news_list):
    counts = {t:0 for t in THEME_KEYWORDS}
    first_link = {t:"" for t in THEME_KEYWORDS}
    for n in news_list:
        text = (n.get("title","") + " " + n.get("desc","")).lower()
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                counts[theme] += 1
                if not first_link[theme]:
                    first_link[theme] = n.get("link","")
    rows=[]
    for t,c in counts.items():
        if c>0:
            rows.append({
                "테마": t, "뉴스건수": c,
                "샘플링크": first_link[t] or "-",
                "대표종목": " · ".join([nm for nm,_ in THEME_STOCKS.get(t, [])]) or "-"
            })
    rows.sort(key=lambda x: x["뉴스건수"], reverse=True)
    return rows

def render_news_compact(news_page, start_idx):
    """제목 + 시간만 아주 컴팩트하게"""
    if not news_page:
        st.info("표시할 뉴스가 없습니다."); return
    for i, n in enumerate(news_page, start=start_idx):
        t = n.get("time","-")
        title = n.get("title","(제목 없음)").strip()
        link = n.get("link","")
        st.markdown(
            f"**{i}. <a href='{link}' target='_blank'>{title}</a>** "
            f"<span style='color:#9aa0a6;font-size:0.85rem'> — {t}</span>",
            unsafe_allow_html=True
        )
