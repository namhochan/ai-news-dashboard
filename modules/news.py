# -*- coding: utf-8 -*-
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import feedparser
from bs4 import BeautifulSoup

KST = ZoneInfo("Asia/Seoul")

# 카테고리
CATEGORIES = {
    "경제뉴스": ["경제", "금리", "물가", "환율", "성장률", "무역"],
    "주식뉴스": ["코스피", "코스닥", "증시", "주가", "외국인 매수", "기관 매매"],
    "산업뉴스": ["반도체", "AI", "배터리", "자동차", "로봇", "수출입"],
    "정책뉴스": ["정책", "정부", "예산", "세금", "규제", "산업부"],
}

# 테마 키워드 & 대표종목(샘플)
THEME_KEYWORDS = {
    "AI": ["ai", "인공지능", "챗봇", "엔비디아", "오픈ai", "생성형"],
    "반도체": ["반도체", "hbm", "칩", "램", "파운드리"],
    "로봇": ["로봇", "자율주행", "협동로봇", "amr"],
    "이차전지": ["배터리", "전고체", "양극재", "음극재", "lfp"],
    "에너지": ["에너지", "정유", "전력", "태양광", "풍력", "가스"],
    "조선": ["조선", "선박", "lng선", "해운"],
    "LNG": ["lng", "가스공사", "터미널"],
    "원전": ["원전", "smr", "원자력", "우라늄"],
    "바이오": ["바이오", "제약", "신약", "임상"],
}

THEME_STOCKS = {
    "AI": [("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"),
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
}

def _clean_html(raw):
    return BeautifulSoup(raw or "", "html.parser").get_text(" ", strip=True)

def _parse_entries(feed, days):
    now = datetime.now(KST)
    items = []
    for e in feed.entries:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = datetime(*e.published_parsed[:6], tzinfo=KST)
        elif getattr(e, "updated_parsed", None):
            pub = datetime(*e.updated_parsed[:6], tzinfo=KST)
        if pub and (now - pub) > timedelta(days=days):
            continue
        title = (e.get("title") or "").strip()
        link = (e.get("link") or "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
        desc = _clean_html(e.get("summary"))
        items.append({"title": title, "link": link, "time": pub.strftime("%Y-%m-%d %H:%M") if pub else "-", "desc": desc})
    return items

def fetch_google_news_by_keyword(keyword, days=3, limit=40):
    url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl=ko&gl=KR&ceid=KR%3Ako"
    feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
    return _parse_entries(feed, days)[:limit]

def fetch_category_news(cat, days=3, max_items=100):
    seen = set(); out = []
    for kw in CATEGORIES.get(cat, []):
        for it in fetch_google_news_by_keyword(kw, days=days, limit=40):
            key = (it["title"], it["link"])
            if key in seen: continue
            seen.add(key); out.append(it)
    # 최신순
    def _k(x):
        try: return datetime.strptime(x["time"], "%Y-%m-%d %H:%M")
        except: return datetime.min
    return sorted(out, key=_k, reverse=True)[:max_items]

def detect_themes(news_list):
    """
    뉴스에서 테마를 감지해 테이블 행 반환.
    return: [{theme, count, avg_delta, leaders, rep_stocks, sample_link}]
    """
    from .market import fetch_quote
    import numpy as np

    counts = {t: 0 for t in THEME_KEYWORDS}
    sample = {t: "" for t in THEME_KEYWORDS}
    for n in news_list:
        text = (n.get("title","") + " " + n.get("desc","")).lower()
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                counts[theme] += 1
                if not sample[theme]:
                    sample[theme] = n.get("link","")

    rows = []
    for theme, c in counts.items():
        if c <= 0: 
            continue
        # 대표 종목 평균 등락률
        deltas = []
        leaders = []
        for name, ticker in THEME_STOCKS.get(theme, []):
            try:
                last, prev = fetch_quote(ticker)
                if last and prev:
                    d = (last - prev) / prev * 100.0
                    deltas.append(d)
                    leaders.append(name)
            except Exception:
                pass
        avg_delta = float(np.mean(deltas)) if deltas else 0.0
        rows.append({
            "테마": theme,
            "뉴스건수": c,
            "평균등락(%)": round(avg_delta, 2),
            "대표종목": " · ".join(leaders[:6]) if leaders else "-",
            "rep_stocks": " · ".join([nm for nm, _ in THEME_STOCKS.get(theme, [])]) or "-",
            "sample_link": sample[theme],
        })
    # 정렬: 뉴스건수 desc → 평균등락 desc
    rows.sort(key=lambda x: (x["뉴스건수"], x["평균등락(%)"]), reverse=True)
    return rows
