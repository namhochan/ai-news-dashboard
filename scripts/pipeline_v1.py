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
    # ---------- [STEP 3] 테마별 종목 → 현재가 + 종목 뉴스 ----------
import yfinance as yf
import re

STOCK_NEWS_DIR = os.path.join(DATA_DIR, "stock_news")
os.makedirs(STOCK_NEWS_DIR, exist_ok=True)

def load_json(path, default=None):
    try:
        return json.load(open(path, "r", encoding="utf-8"))
    except Exception:
        return default

def get_quote_yf(ticker):
    """
    yfinance 현재가(+ 전일 대비 %) 안전하게 가져오기
    """
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        last = info.get("last_price")
        prev = info.get("previous_close")
        if last is None or prev is None:
            # 백업: 최근 5일 일봉에서 종가 2개로 계산
            df = t.history(period="5d", interval="1d")
            if len(df) >= 2:
                last = float(df["Close"].iloc[-1])
                prev = float(df["Close"].iloc[-2])
        if last is None or prev is None or prev == 0:
            return {"price": None, "change_pct": None}
        pct = (float(last) - float(prev)) / float(prev) * 100.0
        return {"price": float(last), "change_pct": round(pct, 2)}
    except Exception:
        return {"price": None, "change_pct": None}

def google_rss_company(name, days=5, max_items=6):
    """
    종목 뉴스 간단 수집: '종목명 주가 OR 뉴스' 검색어로 RSS
    """
    BASE_RSS = "https://news.google.com/rss/search"
    q = f"{name} 주가 OR 뉴스"
    params = {"q": q, "hl": "ko", "gl": "KR", "ceid": "KR:ko"}
    r = requests.get(BASE_RSS, params=params, timeout=20)
    feed = feedparser.parse(r.text)
    now = datetime.now(KST)
    out = []
    for e in feed.entries[: max_items * 2]:
        if hasattr(e, "published_parsed") and e.published_parsed:
            pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc).astimezone(KST)
        else:
            pub = now
        if pub >= now - timedelta(days=days):
            out.append({
                "title": e.title,
                "link": e.link,
                "published": pub.isoformat(timespec="seconds")
            })
        if len(out) >= max_items:
            break
    return out

def step3_collect_stock_data(per_theme=5):
    """
    - theme_top5 + theme_secondary5 읽기
    - theme_stock_map.json 기준으로 테마당 최대 per_theme 종목 선택
    - 각 종목 현재가 + 최신 뉴스 수집 및 저장
    """
    theme_top = load_json(os.path.join(DATA_DIR, "theme_top5.json"), []) or []
    theme_sec = load_json(os.path.join(DATA_DIR, "theme_secondary5.json"), []) or []
    theme_map = load_json(os.path.join(DATA_DIR, "theme_stock_map.json"), {}) or {}

    # 가격 결과 묶음
    price_book = {}

    def key_for_save(kor, ticker):
        # 파일명에 못 쓰는 문자 정리
        base = ticker if ticker and ticker != "—" else kor
        return re.sub(r"[^A-Za-z0-9_.\-가-힣]", "_", base)

    # 두 묶음 처리 함수
    def process_theme_list(theme_list):
        for t in theme_list:
            theme = t.get("theme")
            stocks = (theme_map.get(theme, {}).get("stocks", []) or [])[:per_theme]
            for kor, ticker in stocks:
                # 현재가
                if ticker and ticker != "—":
                    price_book[ticker] = get_quote_yf(ticker)
                # 종목 뉴스
                news = google_rss_company(kor, days=5, max_items=6)
                save_key = key_for_save(kor, ticker)
                json.dump(
                    {"name": kor, "ticker": ticker, "news": news},
                    open(os.path.join(STOCK_NEWS_DIR, f"{save_key}.json"), "w", encoding="utf-8"),
                    ensure_ascii=False, indent=2
                )
                time.sleep(0.2)

    process_theme_list(theme_top)
    process_theme_list(theme_sec)

    # 가격 저장
    json.dump(price_book, open(os.path.join(DATA_DIR, "stock_prices.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return price_book

# ---- main에 3단계 호출 추가 (파일 맨 아래 run() 다음) ----
if __name__ == "__main__":
    # 2단계까지 끝난 상태라면, 3단계만 따로 실행할 수도 있습니다:
    # step3_collect_stock_data()
    pass
