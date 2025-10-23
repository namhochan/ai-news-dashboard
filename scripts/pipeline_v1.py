# scripts/pipeline_v1.py
import os, json, time
from datetime import datetime, timedelta, timezone
from collections import Counter
import requests, feedparser

KST = timezone(timedelta(hours=9))
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# -----------------------
# 1) Google News RSS 수집
# -----------------------
BASE_RSS = "https://news.google.com/rss/search"
SEARCHES = {
    "경제": "경제",
    "정책": "정부 정책 OR 규제 OR 입법",
    "산업": "산업 동향 OR 업계 동향 OR 수주",
    "리포트": "증권사 리포트 OR 애널리스트 리포트 OR 전망 보고서"
}

def google_rss(query, days=3, max_items=50):
    params = {"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    r = requests.get(BASE_RSS, params=params, timeout=20)
    feed = feedparser.parse(r.text)
    now = datetime.now(KST)
    items = []
    for e in feed.entries[: max_items * 2]:
        if hasattr(e, "published_parsed") and e.published_parsed:
            pub_dt = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).astimezone(KST)
        else:
            pub_dt = now
        if pub_dt >= now - timedelta(days=days):
            items.append({
                "title": e.title,
                "link": e.link,
                "published": pub_dt.isoformat(timespec="seconds"),
                "query": query
            })
        if len(items) >= max_items:
            break
    return items

# -----------------------
# 2) 뉴스 4종 수집 → 상단 10 + 전체 100
# -----------------------
def fetch_4_buckets_news():
    all10, all100 = [], []
    for bucket, q in SEARCHES.items():
        items = google_rss(q, days=3, max_items=40)
        all10.extend(items[:3])
        all100.extend(items[:25])
        time.sleep(0.3)
    all10_sorted = sorted(all10, key=lambda x: x["published"], reverse=True)[:10]
    json.dump(all10_sorted, open(os.path.join(DATA_DIR, "headlines_top10.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(all100, open(os.path.join(DATA_DIR, "news_100.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return all10_sorted, all100

# -----------------------
# 3) 테마 키워드 기반 분석
# -----------------------
THEME_KEYWORDS = {
    "AI": ["AI","인공지능","챗GPT","LLM","생성형"],
    "반도체": ["반도체","HBM","메모리","칩"],
    "로봇": ["로봇","로보틱스","휴머노이드"],
    "이차전지": ["2차전지","이차전지","배터리","전고체"],
    "에너지": ["에너지","수소","태양광","풍력","LNG","전력"],
    "조선": ["조선","선박","해양플랜트","LNG선"],
    "원전": ["원전","SMR","원자력"],
    "바이오": ["바이오","제약","신약","임상"]
}

def infer_themes(news_list):
    theme_count = Counter()
    sample_link = {}
    for item in news_list:
        title = item["title"]
        for theme, kws in THEME_KEYWORDS.items():
            if any(kw.lower() in title.lower() for kw in kws):
                theme_count[theme] += 1
                sample_link.setdefault(theme, item["link"])
    ranked = theme_count.most_common()
    top5 = ranked[:5]
    next5 = ranked[5:10]
    out_top = [{"theme": t, "count": c, "sample_link": sample_link[t]} for t, c in top5]
    out_next = [{"theme": t, "count": c, "sample_link": sample_link[t]} for t, c in next5]
    json.dump(out_top, open(os.path.join(DATA_DIR, "theme_top5.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    json.dump(out_next, open(os.path.join(DATA_DIR, "theme_secondary5.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return out_top, out_next

# -----------------------
# MAIN
# -----------------------
def run():
    print("▶ 3일치 뉴스 수집 중…")
    top10, allnews = fetch_4_buckets_news()
    print("▶ 테마 자동분석 중…")
    infer_themes(allnews)
    print("✅ 완료:", datetime.now(KST).isoformat(timespec='seconds'))

if __name__ == "__main__":
    run()
