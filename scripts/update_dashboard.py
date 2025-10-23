# scripts/update_dashboard.py
import os, json, time, math, requests
from datetime import datetime, timedelta
import pytz
import yfinance as yf

# ====== 환경변수(Secrets) ======
NEWS_API_KEY       = os.getenv("NEWSAPI_KEY")          # GitHub Secrets: NEWSAPI_KEY
TELEGRAM_TOKEN     = os.getenv("TELEGRAM_TOKEN")       # GitHub Secrets: TELEGRAM_TOKEN (옵션)
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")     # GitHub Secrets: TELEGRAM_CHAT_ID (옵션)

# ====== 경로 ======
DATA_DIR = "data"
MARKET_PATH   = os.path.join(DATA_DIR, "market_today.json")
THEME_PATH    = os.path.join(DATA_DIR, "theme_top5.json")
KEYWORD_PATH  = os.path.join(DATA_DIR, "keyword_map.json")

# ====== 시간대 ======
KST = pytz.timezone("Asia/Seoul")

# ====== 테마 정의 (원하는대로 수정 가능) ======
THEMES = {
    "AI":           ["AI", "인공지능", "ChatGPT", "LLM"],
    "반도체":        ["반도체", "메모리", "HBM", "파운드리", "ASIC"],
    "로봇":         ["로봇", "로보틱스", "스마트팩토리"],
    "이차전지":      ["이차전지", "배터리", "LFP", "NCM", "리사이클링"],
    "에너지":        ["에너지", "재생에너지", "태양광", "풍력", "수소"],
    "원전/SMR":     ["원전", "원자력", "SMR"],
    "조선/해양":     ["조선", "해양", "선박", "LNG"],
    "바이오":        ["바이오", "제약", "신약"],
    "디지털":        ["디지털", "클라우드", "데이터센터"],
}

# 키워드맵에 쿼리할 키워드 (너무 많으면 쿼터↑)
KEYWORDS_FOR_MAP = [
    "AI","반도체","HBM","메모리","GPU","로봇","스마트팩토리","자동차","조선","LNG","해양","선박",
    "원전","원자력","SMR","양자","이차전지","리사이클링","디지털","바이오","에너지"
]

# ====== 공용 유틸 ======
def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

def month_range_kst():
    """월간 범위(KST). 쿼터 절약하려면 일수를 줄이세요."""
    now = datetime.now(KST)
    start = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    return start, now

def news_api_get(url, params, max_retry=3, timeout=18):
    for i in range(max_retry):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r.json()
            # 쿼터 초과·429 등은 약간 대기 후 재시도
            time.sleep(1.5)
        except requests.RequestException:
            time.sleep(1.5)
    return {"status": "error"}

def build_query_or(words):
    # "AI" OR "로봇" 형태
    return " OR ".join([f'"{w}"' for w in words])

# ====== 페이지네이션으로 기사수 합산 (중요 수정) ======
def count_news_for_keywords(keywords, dt_from, dt_to, max_pages=10):
    if not NEWS_API_KEY:
        return 0
    url = "https://newsapi.org/v2/everything"
    q = build_query_or(keywords)

    total = 0
    page = 1
    page_size = 100
    while page <= max_pages:
        params = {
            "q": q,
            "language": "ko",
            "searchIn": "title,description",
            "from": dt_from.strftime("%Y-%m-%dT%H:%M:%S"),
            "to": dt_to.strftime("%Y-%m-%dT%H:%M:%S"),
            "sortBy": "publishedAt",
            "pageSize": page_size,
            "page": page,
            "apiKey": NEWS_API_KEY,
        }
        data = news_api_get(url, params)
        if data.get("status") != "ok":
            break
        articles = data.get("articles", [])
        total += len(articles)
        if len(articles) < page_size:
            break
        page += 1
        time.sleep(0.35)
    return total

def fetch_latest_headlines(keywords, dt_from, dt_to, limit=10):
    """상위 테마용 최신 헤드라인 수집(중복 타이틀 제거)"""
    if not NEWS_API_KEY:
        return []
    url = "https://newsapi.org/v2/everything"
    q = build_query_or(keywords)
    params = {
        "q": q,
        "language": "ko",
        "searchIn": "title,description",
        "from": dt_from.strftime("%Y-%m-%dT%H:%M:%S"),
        "to": dt_to.strftime("%Y-%m-%dT%H:%M:%S"),
        "sortBy": "publishedAt",
        "pageSize": 100,
        "page": 1,
        "apiKey": NEWS_API_KEY,
    }
    data = news_api_get(url, params)
    if data.get("status") != "ok":
        return []
    seen = set()
    out  = []
    for a in data.get("articles", []):
        title = a.get("title") or ""
        url   = a.get("url")
        if not title or not url:
            continue
        key = title.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": title, "url": url})
        if len(out) >= limit:
            break
    return out

# ====== 지표(KOSPI/KOSDAQ/USD-KRW) ======
def fetch_market_snapshot():
    def last_close_and_change(ticker):
        try:
            df = yf.download(ticker, period="5d", interval="1d", progress=False)
            if df is None or len(df) < 2:
                return None
            last = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2])
            pct  = (last - prev) / prev * 100.0
            return {"value": round(last, 2), "change_pct": round(pct, 2)}
        except Exception:
            return None

    kospi  = last_close_and_change("^KS11")
    kosdaq = last_close_and_change("^KQ11")
    usdkor = last_close_and_change("KRW=X")  # USD/KRW

    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    return {
        "updated_at_kst": now,
        "KOSPI": kospi,
        "KOSDAQ": kosdaq,
        "USD_KRW": usdkor,
        "memo": "원/달러 고평가일수록 환율 수치↑",
    }

def save_json(path, data):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ====== 텔레그램 ======
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=10,
        )
    except requests.RequestException:
        pass

# ====== 메인 파이프라인 ======
def main():
    ensure_dir(DATA_DIR)
    start, end = month_range_kst()

    # 1) 지표
    market = fetch_market_snapshot()
    save_json(MARKET_PATH, market)

    # 2) 테마 집계
    theme_counts = []
    for theme, kws in THEMES.items():
        cnt = count_news_for_keywords(kws, start, end)
        theme_counts.append({"theme": theme, "count": int(cnt)})
    # 상위 5개
    theme_counts_sorted = sorted(theme_counts, key=lambda x: x["count"], reverse=True)
    top5 = theme_counts_sorted[:5]

    # 3) 상위 1개 테마의 최신 헤드라인(Top 10)
    headlines = []
    if top5:
        head = fetch_latest_headlines(THEMES[top5[0]["theme"]], start, end, limit=10)
        headlines = head

    save_json(THEME_PATH, {"updated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                           "themes": theme_counts_sorted,
                           "top5": top5,
                           "headlines": headlines})

    # 4) 월간 키워드 맵 (개별 키워드별 합계)
    keyword_counts = []
    for kw in KEYWORDS_FOR_MAP:
        cnt = count_news_for_keywords([kw], start, end, max_pages=6)  # 키워드당 최대 600건 집계
        keyword_counts.append({"keyword": kw, "count": int(cnt)})
        time.sleep(0.25)
    keyword_counts.sort(key=lambda x: x["count"], reverse=True)
    save_json(KEYWORD_PATH, {"updated_at_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
                             "keywords": keyword_counts})

    # 5) 텔레그램 알림(옵션)
    up = lambda x: f"▲ {x:.2f}%" if x is not None and x >= 0 else f"▼ {abs(x):.2f}%"
    kospi  = market.get("KOSPI")  or {}
    kosdaq = market.get("KOSDAQ") or {}
    fx     = market.get("USD_KRW") or {}

    msg = [
        "📰 AI 뉴스 대시보드 자동갱신 완료",
        f"• KOSPI:  {kospi.get('value','-')} ({up(kospi.get('change_pct')) if 'change_pct' in kospi else '-'})",
        f"• KOSDAQ: {kosdaq.get('value','-')} ({up(kosdaq.get('change_pct')) if 'change_pct' in kosdaq else '-'})",
        f"• 환율:    {fx.get('value','-')} ({up(fx.get('change_pct')) if 'change_pct' in fx else '-'})",
        "",
        "🔥 TOP 5 테마:",
    ]
    for t in top5:
        msg.append(f"  - {t['theme']}: {t['count']}건")
    send_telegram("\n".join(msg))

if __name__ == "__main__":
    main()
