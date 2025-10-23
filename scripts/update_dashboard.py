# scripts/update_dashboard.py
import os, json, time, math
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

import feedparser
import yfinance as yf
import requests

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

KST = timezone(timedelta(hours=9))

# ----- 테마 & 종목 매핑(원하시면 여기만 수정) -----
THEMES = {
    "AI 반도체": {
        "keywords": ["AI", "반도체", "HBM", "메모리", "GPU", "칩"],
        "stocks": ["삼성전자", "하이닉스", "엘비세미콘", "티씨케이"]
    },
    "로봇/스마트팩토리": {
        "keywords": ["로봇", "스마트팩토리", "자동화"],
        "stocks": ["유진로봇", "휴림로봇", "한라캐스트"]
    },
    "조선/해양플랜트": {
        "keywords": ["조선", "LNG", "해양", "선박"],
        "stocks": ["HD현대중공업", "대우조선해양", "대한조선", "삼성중공업"]
    },
    "원전/SMR": {
        "keywords": ["원전", "원자력", "SMR", "원전수출"],
        "stocks": ["두산에너빌리티", "보성파워텍", "한신기계"]
    },
    "2차전지 리사이클링": {
        "keywords": ["이차전지", "2차전지", "리사이클링", "양극재", "음극재"],
        "stocks": ["성일하이텍", "새빗켐", "에코프로"]
    },
}

# ----- 유틸 -----
def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def now_kst_str():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

def try_float(x):
    try:
        return float(x)
    except:
        return None

# ----- 지수/환율 (Yahoo Finance) -----
def fetch_market():
    # KOSPI: ^KS11 / KOSDAQ: ^KQ11(간혹 ^KQ11이 없을 수 있어 대체 로직)
    tickers = {
        "kospi": "^KS11",
        "kosdaq": "^KQ11",
        "usdkor": "KRW=X",  # USDKRW (1 USD = ? KRW)
    }
    out = {"updated_at": now_kst_str(), "kospi": None, "kosdaq": None, "usdkor": None}

    for key, t in tickers.items():
        try:
            y = yf.Ticker(t)
            px = y.fast_info.last_price if hasattr(y, "fast_info") else None
            if px is None:
                hist = y.history(period="1d")
                px = hist["Close"].iloc[-1] if not hist.empty else None
            out[key] = float(px) if px is not None and not math.isnan(px) else None
        except Exception:
            out[key] = None

    # KOSDAQ 대체: ^KOSDAQ / 200지수 등으로 실패시 보정
    if out["kosdaq"] is None:
        for alt in ["^KOSDAQ", "KQ11.KS"]:
            try:
                y = yf.Ticker(alt)
                hist = y.history(period="1d")
                px = hist["Close"].iloc[-1] if not hist.empty else None
                if px:
                    out["kosdaq"] = float(px)
                    break
            except Exception:
                pass

    save_json(os.path.join(DATA_DIR, "market_today.json"), out)
    return out

# ----- 뉴스 수집 (Google News RSS) -----
def google_news_search(query_ko, max_items=20):
    # 예: https://news.google.com/rss/search?q=반도체+주식&hl=ko&gl=KR&ceid=KR:ko
    q = requests.utils.quote(query_ko)
    url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:max_items]:
        title = e.title
        link = getattr(e, "link", None)
        published = getattr(e, "published", "")
        items.append({"title": title, "url": link, "published": published})
    return items

def build_theme_insights():
    # 테마별로 키워드 검색 → 헤드라인 모으기
    theme_data = []
    keyword_counter = Counter()
    per_stock_archive = defaultdict(list)  # 종목 → 최근 2건

    for theme, cfg in THEMES.items():
        all_items = []
        for kw in cfg["keywords"]:
            items = google_news_search(kw, max_items=10)
            all_items.extend(items)
            # 키워드맵 집계
            keyword_counter[kw] += len(items)

        # 테마 설명(간단): 상위 키워드/기사 수 기반
        total_hits = len(all_items)
        desc = f"{theme} 관련 뉴스 빈도 {total_hits}건. 핵심 키워드: {', '.join(cfg['keywords'][:3])}."

        # 대표 뉴스 3건
        top_samples = all_items[:3]

        # 종목별 최신 2건
        for stock in cfg["stocks"]:
            s_items = google_news_search(stock, max_items=5)
            per_stock_archive[stock] = s_items[:2]

        theme_data.append({
            "theme": theme,
            "desc": desc,
            "stocks": cfg["stocks"],
            "score": total_hits,
            "top_news": top_samples
        })

    # 상위 5 테마
    theme_data.sort(key=lambda x: x["score"], reverse=True)
    top5 = theme_data[:5]

    # 저장
    save_json(os.path.join(DATA_DIR, "theme_top5.json"), top5)

    # 키워드맵 (이번 달 기준 단순 누적)
    monthly_keywords = [{"keyword": k, "count": v} for k, v in keyword_counter.most_common(40)]
    save_json(os.path.join(DATA_DIR, "keyword_map.json"), monthly_keywords)

    # 종목별 전 뉴스 2건(아카이브)
    archive = {k: v for k, v in per_stock_archive.items()}
    save_json(os.path.join(DATA_DIR, "stock_archive.json"), archive)

    return top5, monthly_keywords, archive

# ----- 텔레그램 알림(선택) -----
def send_telegram(text):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
    except Exception:
        pass

def main():
    mkt = fetch_market()
    top5, kwmap, arc = build_theme_insights()

    # 간단 알림
    send_telegram(
        "[AI 뉴스 대시보드] 데이터 갱신 완료\n"
        f"- 시간: {now_kst_str()}\n"
        f"- KOSPI: {mkt.get('kospi')} / KOSDAQ: {mkt.get('kosdaq')} / USD/KRW: {mkt.get('usdkor')}\n"
        f"- TOP 테마: {', '.join([t['theme'] for t in top5])}"
    )

if __name__ == "__main__":
    main()
