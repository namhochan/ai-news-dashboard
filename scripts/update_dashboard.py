# scripts/update_dashboard.py
# Google News RSS 기반 자동 테마 추출 + TOP K 선정 + 지수/환율 + 월간 키워드 + 신규 테마 감지
import json, re, time, hashlib
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
import pytz

# ================== 설정 ==================
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")
TOP_K = 5                 # 화면에 노출할 상위 테마 개수
FRESH_WINDOW = "1d"       # TOP 계산에 쓰는 신문 기간 (1d/7d/30d)
MONTHLY_WINDOW = "30d"    # 월간 키워드맵 기간
ALPHA = 0.7               # 감쇠 가중치: 최종점수 = ALPHA*이번집계 + (1-ALPHA)*지난점수
MIN_EMERGE_FREQ = 6       # 신규 테마로 띄울 최소 빈도(바이그램)
MAX_PER_QUERY = 120       # RSS에서 가져올 최대 기사 수

# 테마 카탈로그 (원하는 만큼 확장)
THEMES_CATALOG = {
    "AI":            ["AI","인공지능","ChatGPT","생성형","LLM","오픈AI"],
    "반도체":         ["반도체","HBM","메모리","파운드리","칩","ASIC","GPU"],
    "로봇":          ["로봇","로보틱스","휴머노이드","AGV","AMR"],
    "이차전지":       ["이차전지","2차전지","전고체","배터리","양극재","음극재","리사이클링"],
    "에너지":         ["에너지","태양광","풍력","수소","LNG","재생에너지"],
    "원전":          ["원전","원자력","SMR"],
    "조선/해양":      ["조선","해양","선박","해양플랜트","LNG 운반선"],
    "디스플레이":      ["디스플레이","OLED","마이크로LED","QD"],
    "클라우드":       ["클라우드","데이터센터","하이퍼스케일"],
    "보안":          ["사이버보안","정보보안","랜섬웨어","제로트러스트"],
    "모빌리티":       ["전기차","자율주행","로보택시","LiDAR"],
    "바이오":         ["바이오","신약","임상","제약"],
    "스마트팩토리":     ["스마트팩토리","스마트 공장","FA","자동화"],
}

# 대표 종목 (표시용)
REP_STOCKS = {
    "AI": ["삼성전자","네이버","카카오"],
    "반도체": ["삼성전자","SK하이닉스","엘비세미콘"],
    "로봇": ["레인보우로보틱스","현대로템","유진로봇"],
    "이차전지": ["에코프로","LG에너지솔루션","포스코퓨처엠"],
    "에너지": ["두산에너빌리티","한국전력"],
    "원전": ["보성파워텍","한신기계"],
    "조선/해양": ["HD현대중공업","삼성중공업","한화오션"],
    "디스플레이": ["LG디스플레이","삼성디스플레이(비상장)"],
    "클라우드": ["네이버","NHN","KT"],
    "보안": ["안랩","SK쉴더스(비상장)"],
    "모빌리티": ["현대차","기아","현대로템"],
    "바이오": ["셀트리온","삼성바이오로직스","HLB"],
    "스마트팩토리": ["현대오토에버","한라캐스트"],
}

# ================== RSS 유틸 ==================
def google_news_rss(query: str, when: str = "1d") -> str:
    q = quote_plus(f"{query} when:{when}")
    return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

def clean_text(t: str) -> str:
    t = BeautifulSoup(t or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", t).strip()

def entry_key(entry) -> str:
    base = (entry.get("title","") + entry.get("link","")).encode("utf-8", errors="ignore")
    return hashlib.md5(base).hexdigest()

def fetch_feed(rss_url: str, limit: int = 100) -> list[dict]:
    feed = feedparser.parse(rss_url)
    out, seen = [], set()
    for e in feed.entries[:limit]:
        key = entry_key(e)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "title": clean_text(e.get("title","")),
            "link": e.get("link",""),
            "summary": clean_text(e.get("summary","")),
            "published": e.get("published",""),
        })
    return out

# ================== 데이터 생성 ==================
def build_headlines() -> list[dict]:
    q = "(주식 OR 증시 OR 코스피 OR 코스닥 OR 반도체 OR AI OR 로봇 OR 배터리 OR 조선)"
    items = fetch_feed(google_news_rss(q, "1d"), limit=60)
    return items[:10]

def count_for_keywords(keywords: list[str], when: str, per_query: int) -> tuple[int, str]:
    query = " OR ".join(keywords)
    items = fetch_feed(google_news_rss(query, when), limit=per_query)
    sample = items[0]["link"] if items else ""
    return len(items), sample

def build_theme_counts_dynamic(when=FRESH_WINDOW, per_query=MAX_PER_QUERY, alpha=ALPHA):
    """
    모든 테마 후보에 대해 최신 기사 수 집계 → 지난 점수와 감쇠 결합 → TOP_K만 반환
    """
    rows = []
    for theme, kws in THEMES_CATALOG.items():
        c, sample = count_for_keywords(kws, when, per_query)
        rows.append({"theme": theme, "count": int(c), "sample_link": sample})
        time.sleep(0.2)

    df = pd.DataFrame(rows)
    df["rep_stocks"] = df["theme"].map(lambda t: REP_STOCKS.get(t, []))

    # 지난 점수 불러와 감쇠 결합
    prev_path = DATA_DIR / "theme_all.json"
    if prev_path.exists():
        try:
            prev = pd.read_json(prev_path)
            df = df.merge(prev[["theme","score"]], on="theme", how="left", suffixes=("","_prev"))
            df["score"] = alpha*df["count"] + (1-alpha)*df["score"].fillna(df["count"])
        except Exception:
            df["score"] = df["count"]
    else:
        df["score"] = df["count"]

    # 전체 저장(모니터링용)
    df_all = df.sort_values("score", ascending=False).reset_index(drop=True)
    df_all.to_json(prev_path, force_ascii=False, orient="records", indent=2)

    # 화면용 TOP_K만
    top = df_all.head(TOP_K).to_dict(orient="records")
    return top, df_all

def build_monthly_keywords() -> list[dict]:
    union_keywords = sorted({kw for kws in THEMES_CATALOG.values() for kw in kws})
    query = " OR ".join(union_keywords)
    items = fetch_feed(google_news_rss(query, MONTHLY_WINDOW), limit=300)
    counts = {kw.lower(): 0 for kw in union_keywords}
    for it in items:
        text = (it["title"] + " " + it["summary"]).lower()
        for kw in union_keywords:
            if kw.lower() in text:
                counts[kw.lower()] += 1
    pairs = [{"keyword": k, "count": v} for k, v in counts.items() if v > 0]
    pairs.sort(key=lambda x: x["count"], reverse=True)
    return pairs[:30]

def detect_emerging_themes(when=FRESH_WINDOW, per_query=MAX_PER_QUERY) -> list[dict]:
    """
    신규 테마 감지: 전체 키워드 합성 쿼리로 최근 기사 긁고, 제목/요약에서 바이그램 빈도 상위 노출.
    기존 테마/키워드에 이미 포함된 표현은 제외.
    """
    union_keywords = sorted({kw for kws in THEMES_CATALOG.values() for kw in kws})
    query = " OR ".join(union_keywords)
    items = fetch_feed(google_news_rss(query, when), limit=per_query)

    text = " ".join([clean_text(it["title"] + " " + it["summary"]) for it in items])
    tokens = re.findall(r"[A-Za-z가-힣0-9]{2,}", text)
    # 바이그램 생성
    bigrams = [" ".join(pair) for pair in zip(tokens, tokens[1:])]
    freq = {}
    for bg in bigrams:
        freq[bg] = freq.get(bg, 0) + 1

    # 기존 테마/키워드 제외 필터
    exclude = {k.lower() for kws in THEMES_CATALOG.values() for k in kws}
    emerg = [{"phrase": k, "count": v} for k, v in freq.items()
             if v >= MIN_EMERGE_FREQ and k.lower() not in exclude]
    emerg.sort(key=lambda x: x["count"], reverse=True)
    return emerg[:15]

def build_market_today() -> dict:
    def last_price(ticker: str):
        try:
            df = yf.download(ticker, period="5d", interval="1d", progress=False)
            return float(df["Close"].iloc[-1]) if len(df) else None
        except Exception:
            return None
    kospi = last_price("^KS11")
    kosdaq = last_price("^KQ11")
    usdk = last_price("USDKRW=X")
    return {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "KOSPI": kospi,
        "KOSDAQ": kosdaq,
        "USDKRW": usdk,
    }

def save_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    headlines = build_headlines()
    top, all_df = build_theme_counts_dynamic()
    monthly = build_monthly_keywords()
    emerging = detect_emerging_themes()
    market = build_market_today()

    save_json(DATA_DIR / "headlines.json", headlines)
    save_json(DATA_DIR / "theme_top.json", top)            # 상위 TOP_K
    save_json(DATA_DIR / "theme_all_table.json", json.loads(all_df.to_json(orient="records", force_ascii=False)))
    save_json(DATA_DIR / "keyword_monthly.json", monthly)
    save_json(DATA_DIR / "emerging_themes.json", emerging)
    save_json(DATA_DIR / "market_today.json", market)

if __name__ == "__main__":
    main()
