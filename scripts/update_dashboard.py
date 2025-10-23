import os
import json
import time
from datetime import datetime, timedelta, timezone
from dateutil.relativedelta import relativedelta

import requests
import yfinance as yf

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

NEWS_API_KEY = os.getenv("NEWSAPI_KEY", "").strip()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

KST = timezone(timedelta(hours=9))

# ---------- 유틸 ----------
def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def news_api_get(url, params):
    """NewsAPI 호출(429 대비 간단 재시도)"""
    for i in range(3):
        r = requests.get(url, params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:  # rate limit
            time.sleep(2 + i * 2)
            continue
        r.raise_for_status()
    return {"status": "error", "message": "failed after retries"}

# ---------- 1) 시장지표 ----------
def fetch_market():
    def last_close(ticker):
        try:
            hist = yf.Ticker(ticker).history(period="2d", interval="1d")
            if hist.empty:
                return None, None
            close = float(hist["Close"].dropna().iloc[-1])
            prev = float(hist["Close"].dropna().iloc[-2]) if len(hist) >= 2 else close
            chg = (close - prev) / prev if prev else 0.0
            return close, chg
        except Exception:
            return None, None

    ks, ks_chg = last_close("^KS11")        # 코스피
    kq, kq_chg = last_close("^KQ11")        # 코스닥
    usdkrw, _ = last_close("USDKRW=X")      # 환율

    data = {
        "timestamp_kst": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "KOSPI": {"value": ks, "pct": ks_chg},
        "KOSDAQ": {"value": kq, "pct": kq_chg},
        "USDKRW": {"value": usdkrw},
        "memo": "원/달러 고평가일수록 환율 수치↑"
    }
    save_json(f"{DATA_DIR}/market_today.json", data)
    return data

# ---------- 2) 테마/키워드 ----------
THEMES = {
    "AI": ["AI", "인공지능", "생성AI", "LLM"],
    "반도체": ["반도체", "HBM", "메모리"],
    "로봇": ["로봇", "휴머노이드"],
    "스마트팩토리": ["스마트팩토리", "공장자동화"],
    "조선": ["조선", "선박"],
    "LNG": ["LNG"],
    "해양": ["해양", "해상풍력"],
    "원전": ["원전", "SMR"],
    "이차전지": ["이차전지", "배터리"],
    "리사이클링": ["리사이클링", "재활용"],
    "바이오": ["바이오"],
    "에너지": ["에너지"],
    "디지털": ["디지털"],
}

STOCKS_BY_THEME = {
    "AI": ["삼성전자", "하이닉스", "엘비세미콘", "티씨케이"],
    "로봇": ["유진로봇", "휴림로봇", "한라캐스트"],
    "조선": ["HD현대중공업", "대우조선해양", "대한조선"],
    "원전": ["두산에너빌리티", "보성파워텍", "한신기계"],
    "이차전지": ["에코프로", "성일하이텍", "새빗켐"],
}

def month_range_kst():
    now = datetime.now(KST)
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end = (start + relativedelta(months=1)) - timedelta(seconds=1)
    return start, end

def count_news_for_keywords(keywords, from_kst, to_kst):
    if not NEWS_API_KEY:
        return 0
    url = "https://newsapi.org/v2/everything"
    q = " OR ".join([f'"{k}"' for k in keywords])
    params = {
        "q": q,
        "language": "ko",
        "from": from_kst.strftime("%Y-%m-%dT%H:%M:%S"),
        "to": to_kst.strftime("%Y-%m-%dT%H:%M:%S"),
        "pageSize": 100,
        "apiKey": NEWS_API_KEY,
        "sortBy": "publishedAt",
    }
    data = news_api_get(url, params)
    if data.get("status") != "ok":
        return 0
    # totalResults는 1000 상한/샘플링 이슈가 있어 실제 기사 수 집계 기준은 articles 길이 합산
    return len(data.get("articles", []))

def build_theme_top5():
    start, end = month_range_kst()
    records = []
    for theme, kws in THEMES.items():
        cnt = count_news_for_keywords(kws, start, end)
        records.append({"theme": theme, "count": int(cnt)})
        # API rate-limit 완화
        time.sleep(0.4)
    # 정렬 후 상위 5개
    records.sort(key=lambda x: x["count"], reverse=True)
    top5 = records[:5]
    save_json(f"{DATA_DIR}/theme_top5.json", {"timestamp_kst": datetime.now(KST).isoformat(), "items": top5})
    return top5

def build_keyword_map():
    start, end = month_range_kst()
    items = []
    for theme, kws in THEMES.items():
        cnt = count_news_for_keywords(kws, start, end)
        items.append({"keyword": theme, "count": int(cnt)})
        time.sleep(0.3)
    save_json(f"{DATA_DIR}/keyword_map.json", {"timestamp_kst": datetime.now(KST).isoformat(), "items": items})
    return items

# ---------- 3) 최근 헤드라인 ----------
def fetch_recent_headlines(limit=10):
    if not NEWS_API_KEY:
        return []
    url = "https://newsapi.org/v2/top-headlines"
    params = {
        "country": "kr",
        "category": "business",
        "pageSize": limit,
        "apiKey": NEWS_API_KEY,
    }
    data = news_api_get(url, params)
    if data.get("status") != "ok":
        return []
    out = []
    for a in data.get("articles", []):
        out.append({"title": a.get("title"), "url": a.get("url"), "source": a.get("source", {}).get("name")})
    save_json(f"{DATA_DIR}/recent_headlines.json", {"timestamp_kst": datetime.now(KST).isoformat(), "items": out})
    return out

# ---------- 4) 텔레그램 알림 ----------
def send_telegram(msg):
    if not (TG_TOKEN and TG_CHAT_ID):
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": TG_CHAT_ID, "text": msg, "disable_web_page_preview": True}, timeout=20)
    try:
        r.raise_for_status()
    except Exception as e:
        print("Telegram send error:", r.text)

def main():
    mk = fetch_market()
    top5 = build_theme_top5()
    kw = build_keyword_map()
    heads = fetch_recent_headlines(10)

    # 텔레그램 메시지
    up = []
    if mk.get("KOSPI", {}).get("value") is not None:
        up.append(f"KOSPI {mk['KOSPI']['value']:.2f} ({mk['KOSPI']['pct']*100:+.2f}%)")
    if mk.get("KOSDAQ", {}).get("value") is not None:
        up.append(f"KOSDAQ {mk['KOSDAQ']['value']:.2f} ({mk['KOSDAQ']['pct']*100:+.2f}%)")
    if mk.get("USDKRW", {}).get("value") is not None:
        up.append(f"USD/KRW {mk['USDKRW']['value']:.2f}")

    theme_line = ", ".join([f"{x['theme']}({x['count']})" for x in top5]) if top5 else "데이터 없음"
    msg = "📊 대시보드 갱신 완료\n" + " / ".join(up) + f"\n🔥 Top5: {theme_line}"
    send_telegram(msg)

if __name__ == "__main__":
    main()
