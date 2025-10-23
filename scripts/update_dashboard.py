# scripts/update_dashboard.py
import os, re, json, time, math
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict
import feedparser
import pandas as pd

KST = timezone(timedelta(hours=9))

# ====== 설정 ======
THEMES = [
    "AI","반도체","로봇","이차전지","에너지","원전","조선","해양","디스플레이",
    "데이터센터","보안","모빌리티","바이오","스마트팩토리"
]
NEWS_PER_THEME = 80           # 테마별 최대 기사 수집
DAYS_LOOKBACK = 2             # 최근 N일 기사만 사용
TOP_THEMES = 5                # 상단 차트 갯수
TOP_KEYWORDS_PER_THEME = 4    # 테마별 대표 키워드(회사/명사) 최대 갯수
DATA_DIR = "data"

# 한국어 기업/조직명에 자주 쓰이는 접미사/단어(간단 규칙)
KOR_ORG_SUFFIX = (
    "전자|하이텍|하이닉스|솔루션|시스템|로보틱스|엔터|제약|바이오|화학|중공업|조선|해운|항공|에너지|파워|건설|기계|소프트|테크|모빌리티|반도체|디스플레이"
)

STOPWORDS = set([
    "기자","사진","제공","관련","분야","업계","시장","기업","산업","오늘","국내","해외","업체",
    "사실","대표","최근","정부","한국","대한민국","뉴스","헤드라인","증권","코스피","코스닥","환율",
])

def ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def google_news_rss(query: str):
    # 한국어 뉴스, 최근순
    return f"https://news.google.com/rss/search?q={query}+when:7d&hl=ko&gl=KR&ceid=KR:ko"

def within_days(published_parsed, days=DAYS_LOOKBACK):
    if not published_parsed:
        return False
    dt = datetime(*published_parsed[:6], tzinfo=timezone.utc).astimezone(KST)
    return dt >= (datetime.now(KST) - timedelta(days=days))

def normalize_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_org_keywords(text: str, topn=TOP_KEYWORDS_PER_THEME):
    """
    매우 가벼운 규칙 기반 추출:
    - 한글 2글자 이상 단어
    - 기업/조직명 접미사 패턴 또는 고유명사 형태(첫글자 대문자 영문 포함)
    - 불용어 제거 후 상위 n개
    """
    # 한글/영문/숫자만 남기고 분절
    tokens = re.findall(r"[A-Za-z0-9가-힣]{2,}", text)
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) <= 20]

    # 기업/조직 가능성: 접미사 매칭 or 영문 대문자 시작 토큰
    org_like = []
    suf = re.compile(rf"({KOR_ORG_SUFFIX})$")
    for t in tokens:
        if suf.search(t) or re.match(r"^[A-Z][A-Za-z0-9\-]{1,}$", t):
            org_like.append(t)

    if not org_like:
        # 접미사 매칭 못 찾으면 상위 빈도 일반명사에서 고름(완전 자동)
        cnt = Counter(tokens)
    else:
        cnt = Counter(org_like)

    return [w for w,_ in cnt.most_common(topn)]

def fetch_theme_news(theme: str):
    url = google_news_rss(theme)
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:NEWS_PER_THEME]:
        if not within_days(getattr(e, "published_parsed", None)):
            continue
        title = normalize_text(getattr(e, "title", ""))
        summary = normalize_text(getattr(e, "summary", ""))
        link = getattr(e, "link", "")
        items.append({"title": title, "summary": summary, "link": link, "theme": theme})
    return items

def build_corpus():
    corpus = []
    for t in THEMES:
        try:
            corpus.extend(fetch_theme_news(t))
            time.sleep(0.4)  # 과도한 호출 방지
        except Exception:
            continue
    return corpus

def aggregate(corpus):
    # 테마별 기사수
    theme_count = Counter([it["theme"] for it in corpus])

    # 테마별 대표 키워드(회사/고유명사) 자동 추출
    theme_keywords = defaultdict(list)
    for t in THEMES:
        texts = " ".join([f'{it["title"]} {it["summary"]}' for it in corpus if it["theme"]==t])
        if texts:
            theme_keywords[t] = extract_org_keywords(texts)
        else:
            theme_keywords[t] = []

    # 최근 헤드라인 Top 10 (전체에서 최신 10건)
    # published 정보가 feedparser마다 다를 수 있어 여기서는 단순 앞부분 사용
    headlines = [{"title": it["title"], "link": it["link"]} for it in corpus[:10]]

    # 월간(최근 기간) 키워드 맵: 모든 테마 합산으로 키워드 상위 n
    all_text = " ".join([f'{it["title"]} {it["summary"]}' for it in corpus])
    monthly_keywords = Counter(re.findall(r"[A-Za-z0-9가-힣]{2,}", all_text))
    for sw in list(STOPWORDS):
        monthly_keywords.pop(sw, None)
    monthly = [{"keyword": w, "count": c} for w, c in monthly_keywords.most_common(30)]

    # Top N 테마 선정(기사수 기준)
    ranked_themes = theme_count.most_common()
    top_themes = [t for t,_ in ranked_themes[:TOP_THEMES]]

    # 표시용 데이터프레임
    theme_df = pd.DataFrame(
        [{"theme": t, "count": theme_count.get(t,0),
          "score": theme_count.get(t,0),   # 간단히 count를 점수로 사용
          "rep_keywords": " · ".join(theme_keywords.get(t,[]))} for t in THEMES]
    ).sort_values("count", ascending=False).reset_index(drop=True)

    return {
        "theme_df": theme_df,
        "top_themes": top_themes,
        "headlines": headlines,
        "monthly": monthly
    }

def save_json(name, obj):
    with open(os.path.join(DATA_DIR, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def main():
    ensure_dir()
    corpus = build_corpus()
    agg = aggregate(corpus)

    # 파일 저장
    save_json("theme_top5.json", {
        "generated_at": datetime.now(KST).isoformat(),
        "top_themes": agg["top_themes"],
        "theme_table": agg["theme_df"].to_dict(orient="records")
    })
    save_json("keyword_map.json", {"monthly": agg["monthly"]})
    save_json("headlines.json", {"items": agg["headlines"]})

if __name__ == "__main__":
    main()
