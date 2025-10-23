
import json, os, re
from datetime import datetime
from collections import Counter
import pytz, requests, feedparser, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(__file__))
DATA = os.path.join(ROOT, "data")
KST = pytz.timezone("Asia/Seoul")

def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ---------- 1) market ----------
def fetch_market_today():
    tickers = {
        "KOSPI": "^KS11",
        "KOSDAQ": "^KQ11",
        "USD_KRW": "KRW=X",
        "WTI": "CL=F",
        "Gold": "GC=F",
    }
    out = {}
    for k, t in tickers.items():
        try:
            df = yf.download(t, period="10d", interval="1d", progress=False).dropna()
            last = float(df["Close"].iloc[-1])
            prev = float(df["Close"].iloc[-2]) if len(df) >= 2 else last
            delta = last - prev
            pct = (delta / prev * 100) if prev else 0.0
            out[k] = {"value": last, "delta": delta, "pct": pct}
        except Exception:
            pass
    comment = []
    try:
        if out.get("USD_KRW", {}).get("value", 0) >= 1400: comment.append("원/달러 고평가")
        if out.get("WTI", {}).get("value", 0) >= 85: comment.append("유가 강세")
    except Exception:
        pass
    out["comment"] = " · ".join(comment) if comment else "혼조"
    return out

# ---------- 2) headlines (RSS) ----------
NEWS_SOURCES = [
    "https://news.google.com/rss/search?q=AI%20%EB%B0%98%EB%8F%84%EC%B2%B4&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%EB%A1%9C%EB%B4%87%20%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%8C%A9%ED%86%A0%EB%A6%AC&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%EC%A1%B0%EC%84%A0%20LNG%20%ED%95%B4%EC%96%91%ED%94%8C%EB%9E%9C%ED%8A%B8&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=ESS%20%EB%B0%B0%ED%84%B0%EB%A6%AC&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%EC%9B%90%EC%A0%84%20SMR&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%ED%95%9C%EA%B5%AD%20%EC%A6%9D%EC%8B%9C&hl=ko&gl=KR&ceid=KR:ko",
]
KEYWORDS = ["AI","반도체","HBM","로봇","스마트팩토리","조선","LNG","해양","ESS","배터리","전력","원전","SMR","수소","환율","수출","바이오","게임"]

def collect_headlines():
    items = []
    for url in NEWS_SOURCES:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:30]:
                title = re.sub(r"\s+", " ", getattr(e, "title", "") or "")
                link  = getattr(e, "link", "")
                pub   = getattr(e, "published", "") or getattr(e, "updated", "")
                src   = getattr(getattr(e, "source", None), "title", "") if hasattr(e, "source") else ""
                if title and link:
                    items.append({"title": title, "url": link, "published": pub, "source": src})
        except Exception:
            continue
    return items

def build_keyword_map(headlines):
    cnt = Counter()
    for item in headlines:
        low = (item.get("title") or "").lower()
        for kw in KEYWORDS:
            if kw.lower() in low:
                cnt[kw] += 1
    return dict(cnt.most_common(20))

# ---------- 3) themes ----------
THEME_DEF = [
    {"name":"AI 반도체", "keys":["AI","반도체","HBM"], "stocks":["삼성전자","하이닉스","엘비세미콘","티씨케이"]},
    {"name":"로봇/스마트팩토리", "keys":["로봇","스마트팩토리"], "stocks":["유진로봇","휴림로봇","한라캐스트"]},
    {"name":"조선/해양플랜트", "keys":["조선","LNG","해양"], "stocks":["HD현대중공업","대한조선","삼성중공업"]},
    {"name":"ESS/배터리", "keys":["ESS","배터리","전력"], "stocks":["씨아이에스","엠플러스","천보","코스모신소재"]},
    {"name":"원전/SMR", "keys":["원전","SMR"], "stocks":["두산에너빌리티","보성파워텍","한신기계"]},
]
def make_theme_top5(kw_map):
    scored = []
    for t in THEME_DEF:
        score = sum(kw_map.get(k,0) for k in t["keys"])
        scored.append((score, t))
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for sc, t in scored[:5]:
        out.append({
            "name": t["name"],
            "strength": min(int(sc*4+60), 100),
            "summary": f"{t['name']} 관련 뉴스 빈도 상승. 핵심 키워드: {', '.join(t['keys'])}.",
            "stocks": t["stocks"],
            "news_link": "https://news.google.com/?hl=ko&gl=KR&ceid=KR:ko",
        })
    return out

# ---------- main ----------
def main():
    market = fetch_market_today()
    heads  = collect_headlines()
    kwmap  = build_keyword_map(heads)
    themes = make_theme_top5(kwmap)

    os.makedirs(DATA, exist_ok=True)
    save_json(os.path.join(DATA, "market_today.json"), market)
    save_json(os.path.join(DATA, "headlines.json"), heads[:60])
    save_json(os.path.join(DATA, "keyword_map.json"), kwmap)
    save_json(os.path.join(DATA, "theme_top5.json"), themes)

    print("[Updater] done", datetime.now(KST).strftime("%Y-%m-%d %H:%M"))

if __name__ == "__main__":
    main()
