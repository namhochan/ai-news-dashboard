# scripts/update_dashboard.py
import os, json, time, argparse
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
import requests

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

KST = timezone(timedelta(hours=9))

# --- 유틸 ---
def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_json(path, default=None):
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def pct(a, b):
    try:
        return round((a-b)/b*100, 2)
    except Exception:
        return None

# --- 1) 지수/환율 수집 ---
def fetch_market():
    # 야후 파이낸스 티커
    tickers = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "USDKRW": "KRW=X",
    }
    out = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")}
    for name, t in tickers.items():
        try:
            data = yf.Ticker(t).history(period="5d", interval="1d")
            if data.empty:
                out[name] = {"value": None, "change": None}
                continue
            last = float(data["Close"].iloc[-1])
            prev = float(data["Close"].iloc[-2]) if len(data) > 1 else last
            out[name] = {
                "value": round(last, 2),
                "change_pct": pct(last, prev),
                "dir": "▲" if last >= prev else "▼",
            }
        except Exception:
            out[name] = {"value": None, "change": None}
    save_json(os.path.join(DATA_DIR, "market_today.json"), out)
    return out

# --- 2) 뉴스 헤드라인(Optional: NEWSAPI) + 키워드맵/테마 Top5 간이 생성 ---
KEYWORDS = [
    "AI","반도체","로봇","이차전지","원전","바이오","에너지","조선","해양","디지털","수소","전기차","장비"
]

def fetch_headlines():
    key = os.environ.get("NEWSAPI_KEY")
    headlines = []
    if key:
        try:
            url = ("https://newsapi.org/v2/top-headlines?"
                   "country=kr&pageSize=40&apiKey="+key)
            r = requests.get(url, timeout=15)
            j = r.json()
            for it in j.get("articles", []):
                title = it.get("title") or ""
                url_ = it.get("url") or ""
                if title and url_:
                    headlines.append({"title": title, "url": url_})
        except Exception:
            pass
    # 키가 없거나 실패하면 기존 아카이브 유지
    if not headlines:
        headlines = load_json(os.path.join(DATA_DIR, "recent_headlines.json"), [])
    # 상위 20개만 유지
    headlines = (headlines or [])[:20]
    save_json(os.path.join(DATA_DIR, "recent_headlines.json"), headlines)
    return headlines

def build_keyword_map(headlines):
    from collections import Counter
    cnt = Counter()
    for h in headlines:
        title = h["title"]
        for k in KEYWORDS:
            if k in title:
                cnt[k] += 1
    # 기본값
    if not cnt:
        for k in KEYWORDS: cnt[k]=0
    items = [{"keyword": k, "count": c} for k,c in cnt.most_common()]
    save_json(os.path.join(DATA_DIR, "keyword_map.json"), items)
    return items

def build_theme_top5(keyword_items):
    # count 기준 상위 5개
    sorted_kw = sorted(keyword_items, key=lambda x: x["count"], reverse=True)
    top5 = [{"theme": it["keyword"], "score": int(it["count"])} for it in sorted_kw[:5]]
    if not top5:
        top5 = [{"theme": "AI 반도체", "score": 10}]
    save_json(os.path.join(DATA_DIR, "theme_top5.json"), top5)
    return top5

# --- 3) 텔레그램용 요약 ---
def build_summary(market, top5, headlines):
    kospi = market.get("KOSPI", {})
    kosdaq = market.get("KOSDAQ", {})
    usdkrw = market.get("USDKRW", {})

    lines = []
    lines.append("*AI 뉴스 대시보드 업데이트*")
    lines.append(f"🕒 {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} (KST)")
    # 지수
    def fmt(name, d):
        v = d.get("value")
        cp = d.get("change_pct")
        arrow = d.get("dir","")
        if v is None or cp is None: return f"- {name}: 데이터 없음"
        sign = "+" if cp>=0 else ""
        return f"- {name}: {v} ({arrow} {sign}{cp}%)"
    lines.append(fmt("KOSPI", kospi))
    lines.append(fmt("KOSDAQ", kosdaq))
    lines.append(fmt("USDKRW", usdkrw))
    # 테마
    if top5:
        themes = ", ".join([t["theme"] for t in top5])
        lines.append(f"🔥 Top5 테마: {themes}")
    # 헤드라인
    if headlines:
        lines.append(f"📰 헤드라인 {len(headlines)}건 반영")
    return "\n".join(lines)

def main(summary_only=False):
    market = load_json(os.path.join(DATA_DIR, "market_today.json"))
    if not summary_only:
        market = fetch_market()
        headlines = fetch_headlines()
        kw = build_keyword_map(headlines)
        top5 = build_theme_top5(kw)
    else:
        headlines = load_json(os.path.join(DATA_DIR, "recent_headlines.json"), [])
        kw = load_json(os.path.join(DATA_DIR, "keyword_map.json"), [])
        top5 = load_json(os.path.join(DATA_DIR, "theme_top5.json"), [])

    msg = build_summary(market or {}, top5 or [], headlines or [])
    print(msg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    main(summary_only=args.summary_only)
