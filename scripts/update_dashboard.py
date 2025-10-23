# scripts/update_dashboard.py
# 하나의 대형 RSS 풀을 내려받아 기사 내용을 테마 사전으로 분류하는 방식
import json, re, time, hashlib
from pathlib import Path
from datetime import datetime
from urllib.parse import quote_plus

import feedparser
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup
import pytz

# ---------------- 기본 설정 ----------------
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

KST = pytz.timezone("Asia/Seoul")

FRESH_WINDOW = "1d"     # 대시보드 실시간 집계용 기간
MONTHLY_WINDOW = "30d"  # 월간 키워드맵 기간
TOP_K = 5               # 상위 테마 노출 개수
ALPHA = 0.6             # 감쇠 가중치 (이번:지난 = 0.6:0.4)
MAX_ITEMS_DAY = 250     # 하루치 RSS 최대 수집량
MAX_ITEMS_MONTH = 400   # 월간 RSS 최대 수집량

# 테마 사전 (필요시 계속 추가/수정)
THEMES_CATALOG = {
    "AI":            ["ai","인공지능","chatgpt","생성형","llm","오픈ai","gpt-"],
    "반도체":         ["반도체","hbm","메모리","파운드리","칩","asic","gpu","tsmc","웨이퍼"],
    "로봇":          ["로봇","로보틱스","휴머노이드","amr","agv"],
    "이차전지":       ["2차전지","이차전지","전고체","배터리","양극재","음극재","리사이클링","전해질"],
    "에너지":         ["에너지","태양광","풍력","수소","lng","재생에너지","전력수급"],
    "원전":          ["원전","원자력","smr","핵연료"],
    "조선/해양":      ["조선","해양","선박","해양플랜트","lng 운반선","조선소"],
    "디스플레이":      ["디스플레이","oled","마이크로led","qd"],
    "클라우드":       ["클라우드","데이터센터","하이퍼스케일","co-location","colocation"],
    "보안":          ["사이버보안","정보보안","랜섬웨어","제로트러스트"],
    "모빌리티":       ["전기차","ev","자율주행","로보택시","lidar","배터리팩"],
    "바이오":         ["바이오","신약","임상","제약","임상시험"],
    "스마트팩토리":     ["스마트팩토리","fa","공장 자동화","mes","plc"],
}

REP_STOCKS = {
    "AI": ["삼성전자","네이버","카카오"],
    "반도체": ["삼성전자","SK하이닉스","엘비세미콘"],
    "로봇": ["레인보우로보틱스","현대로템","유진로봇"],
    "이차전지": ["에코프로","LG에너지솔루션","포스코퓨처엠"],
    "에너지": ["두산에너빌리티","한국전력"],
    "원전": ["보성파워텍","한신기계"],
    "조선/해양": ["HD현대중공업","삼성중공업","한화오션"],
    "디스플레이": ["LG디스플레이"],
    "클라우드": ["네이버","KT","NHN"],
    "보안": ["안랩"],
    "모빌리티": ["현대차","기아"],
    "바이오": ["셀트리온","삼성바이오로직스"],
    "스마트팩토리": ["현대오토에버"],
}

STOPWORDS = {"그리고","그러나","하지만","한국","국내","관련","업계","회사","시장","산업","분야"}

# ---------------- 유틸 ----------------
def google_news_rss(query: str, when: str = "1d") -> str:
    q = quote_plus(f"{query} when:{when}")
    return f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

def clean_text(t: str) -> str:
    t = BeautifulSoup(t or "", "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", t).strip()

def fetch_feed(rss_url: str, limit: int) -> list[dict]:
    feed = feedparser.parse(rss_url)
    seen, items = set(), []
    for e in feed.entries[:limit]:
        uid = hashlib.md5((e.get("title","") + e.get("link","")).encode("utf-8","ignore")).hexdigest()
        if uid in seen: 
            continue
        seen.add(uid)
        items.append({
            "title": clean_text(e.get("title","")),
            "summary": clean_text(e.get("summary","")),
            "link": e.get("link",""),
            "published": e.get("published",""),
        })
    return items

def big_union_query() -> str:
    # 너무 폭넓으면 노이즈가 커져서 ‘주식/산업/기업’ 위주의 한글 키워드로 축소
    base = "(주식 OR 증시 OR 코스피 OR 코스닥 OR 산업 OR 기업 OR 테크 OR 기술 OR 반도체 OR AI OR 로봇 OR 배터리 OR 조선 OR 에너지 OR 원전)"
    return base

# ---------------- 집계 로직 ----------------
def classify_by_theme(items: list[dict]) -> pd.DataFrame:
    # 각 기사에 대해 테마 매칭(복수 테마 가능), 테마별 고유 기사 수 집계
    rows = []
    for it in items:
        text = (it["title"] + " " + it["summary"]).lower()
        matched = []
        for theme, kws in THEMES_CATALOG.items():
            for kw in kws:
                if kw.lower() in text:
                    matched.append(theme)
                    break
        for theme in set(matched):
            rows.append({"theme": theme, "link": it["link"]})
    if not rows:
        return pd.DataFrame(columns=["theme","count"])
    df = pd.DataFrame(rows).drop_duplicates()
    cnt = df.groupby("theme").size().reset_index(name="count")
    return cnt

def build_fresh_themes():
    # 큰 풀에서 당일 아이템 수집
    items = fetch_feed(google_news_rss(big_union_query(), FRESH_WINDOW), limit=MAX_ITEMS_DAY)
    counts = classify_by_theme(items)
    if counts.empty:
        counts = pd.DataFrame([{"theme": t, "count": 0} for t in THEMES_CATALOG.keys()])

    # 감쇠 적용
    prev_path = DATA_DIR / "theme_all.json"
    if prev_path.exists():
        prev = pd.read_json(prev_path)
    else:
        prev = pd.DataFrame(columns=["theme","score"])
    df = counts.merge(prev[["theme","score"]], on="theme", how="left")
    df["score"] = ALPHA*df["count"] + (1-ALPHA)*df["score"].fillna(df["count"])

    # 대표종목/샘플링크 추가
    df["rep_stocks"] = df["theme"].map(lambda t: REP_STOCKS.get(t, []))
    # 샘플링크는 최신 기사에서 해당 테마 키워드가 포함된 첫 링크
    sample_links = {}
    for it in items:
        text = (it["title"] + " " + it["summary"]).lower()
        for theme, kws in THEMES_CATALOG.items():
            if theme in sample_links: 
                continue
            if any(kw.lower() in text for kw in kws):
                sample_links[theme] = it["link"]
    df["sample_link"] = df["theme"].map(lambda t: sample_links.get(t, ""))

    # 전체 저장(내부/모니터링)
    df_all = df.sort_values("score", ascending=False).reset_index(drop=True)
    df_all.to_json(prev_path, orient="records", force_ascii=False, indent=2)

    # TOP_K 화면용
    top = df_all.head(TOP_K).to_dict(orient="records")
    return top, df_all

def build_monthly_keywords():
    items = fetch_feed(google_news_rss(big_union_query(), MONTHLY_WINDOW), limit=MAX_ITEMS_MONTH)
    tokens = []
    for it in items:
        text = clean_text(it["title"] + " " + it["summary"])
        for tok in re.findall(r"[A-Za-z가-힣0-9]{2,}", text):
            tl = tok.lower()
            if tl in STOPWORDS: 
                continue
            tokens.append(tl)
    freq = pd.Series(tokens).value_counts()
    freq = freq[freq >= 3]  # 너무 희귀한 토큰 제거
    df = pd.DataFrame({"keyword": freq.index, "count": freq.values})
    # 너무 일반적인 단어들 정리
    ban = {"ai","인공지능","기업","산업","증시","주식"}
    df = df[~df["keyword"].isin(ban)].head(30)
    return df.to_dict(orient="records")

def detect_emerging_themes():
    # 월간 데이터에서 바이그램 빈도 상위 추출(기존 테마/키워드 제외)
    items = fetch_feed(google_news_rss(big_union_query(), MONTHLY_WINDOW), limit=MAX_ITEMS_MONTH)
    union_kws = {kw.lower() for kws in THEMES_CATALOG.values() for kw in kws}
    text = " ".join(clean_text(it["title"] + " " + it["summary"]) for it in items)
    toks = re.findall(r"[A-Za-z가-힣0-9]{2,}", text.lower())
    bigrams = [" ".join(p) for p in zip(toks, toks[1:])]
    s = pd.Series(bigrams).value_counts()
    s = s[s >= 5]  # 최소 빈도
    df = pd.DataFrame({"phrase": s.index, "count": s.values})
    df = df[~df["phrase"].isin(union_kws)].head(15)
    return df.to_dict(orient="records")

def build_market_today():
    def last_price(ticker: str):
        try:
            df = yf.download(ticker, period="5d", interval="1d", progress=False)
            return float(df["Close"].iloc[-1]) if len(df) else None
        except Exception:
            return None
    return {
        "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "KOSPI": last_price("^KS11"),
        "KOSDAQ": last_price("^KQ11"),
        "USDKRW": last_price("USDKRW=X"),
    }

def save_json(name: str, obj):
    (DATA_DIR / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    market = build_market_today()
    top, all_df = build_fresh_themes()
    monthly = build_monthly_keywords()
    emerg = detect_emerging_themes()

    save_json("market_today.json", market)
    save_json("theme_top.json", top)
    save_json("theme_all_table.json", json.loads(all_df.to_json(orient="records", force_ascii=False)))
    save_json("keyword_monthly.json", monthly)
    save_json("emerging_themes.json", emerg)

    # 헤드라인 10개(보기용)
    heads = fetch_feed(google_news_rss(big_union_query(), "1d"), limit=80)[:10]
    save_json("headlines.json", heads)

if __name__ == "__main__":
    main()
