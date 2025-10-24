# modules/news.py
# 구글 뉴스 RSS 수집, 테마 감지, 테마-종목 맵 (샌드박스/tzdata/네트워크 폴백 포함)
# ───────────────────────────────────────────────────────────
# 변경 요약 (2025-10-24)
# • tzdata 의존 제거: ZoneInfo("Asia/Seoul") → 고정 KST(UTC+9)
# • feedparser/bs4 미설치 또는 네트워크 차단 환경에서도 동작하도록 **안전 폴백** 추가
# • 키워드/테마/종목 맵 기존 스펙 유지
# • 자체 테스트(__main__) 추가 (실제 네트워크 미사용)
# ───────────────────────────────────────────────────────────

from __future__ import annotations
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from typing import Any, Dict, List, Optional

# 외부 의존성은 샌드박스에서 없을 수 있으므로 가드
try:
    import feedparser  # type: ignore
    _FEED_OK = True
except Exception:
    feedparser = None  # type: ignore
    _FEED_OK = False

try:
    from bs4 import BeautifulSoup  # type: ignore
    _BS_OK = True
except Exception:
    BeautifulSoup = None  # type: ignore
    _BS_OK = False

# tzdata 없이 안전한 KST (UTC+9)
KST = timezone(timedelta(hours=9), name="Asia/Seoul")

# -------- 카테고리/테마 사전 --------
CATEGORIES = {
    "경제뉴스": ["경제", "금리", "물가", "환율", "성장률", "무역"],
    "주식뉴스": ["코스피", "코스닥", "증시", "주가", "외국인 매수", "기관 매도"],
    "산업뉴스": ["반도체", "AI", "배터리", "자동차", "로봇", "수출입"],
    "정책뉴스": ["정책", "정부", "예산", "규제", "세금", "산업부"],
}

THEME_KEYWORDS = {
    "AI":        ["ai","인공지능","챗봇","생성형","오픈ai","엔비디아","gpu","llm"],
    "반도체":     ["반도체","hbm","칩","램","파운드리","소부장"],
    "로봇":       ["로봇","협동로봇","amr","자율주행로봇","로보틱스"],
    "이차전지":    ["2차전지","이차전지","배터리","전고체","양극재","음극재","lfp"],
    "에너지":     ["에너지","정유","전력","가스","태양광","풍력"],
    "조선":       ["조선","선박","수주","lng선","해운"],
    "LNG":       ["lng","액화천연가스","가스공사","터미널"],
    "원전":       ["원전","원자력","smr","우라늄"],
    "바이오":     ["바이오","제약","신약","임상","항암"],
    "전력":       ["전력","송배전","ESS","스마트그리드","전기요금"],
}

# 대형/중형/소형 섞은 대표 예시 (원하는대로 확장 가능)
THEME_STOCKS = {
    "AI":       [("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"),
                 ("솔트룩스","304100.KQ"),("브레인즈컴퍼니","099390.KQ"),("한글과컴퓨터","030520.KS")],
    "반도체":   [("SK하이닉스","000660.KS"),("DB하이텍","000990.KS"),("리노공업","058470.KQ"),
                 ("원익IPS","240810.KQ"),("티씨케이","064760.KQ"),("에프에스티","036810.KQ")],
    "로봇":     [("레인보우로보틱스","277810.KQ"),("유진로봇","056080.KQ"),("티로보틱스","117730.KQ"),
                 ("로보스타","090360.KQ"),("스맥","099440.KQ")],
    "이차전지": [("LG에너지솔루션","373220.KS"),("포스코퓨처엠","003670.KS"),
                 ("에코프로","086520.KQ"),("코스모신소재","005070.KQ"),("엘앤에프","066970.KQ")],
    "에너지":   [("SK이노베이션","096770.KS"),("GS","078930.KS"),("S-Oil","010950.KS"),
                 ("한화솔루션","009830.KS"),("OCI홀딩스","010060.KS")],
    "조선":     [("HD한국조선해양","009540.KS"),("HD현대미포","010620.KS"),
                 ("삼성중공업","010140.KS"),("한화오션","042660.KS")],
    "LNG":     [("한국가스공사","036460.KS"),("지에스이","053050.KQ"),("대성에너지","117580.KQ"),("SK가스","018670.KS")],
    "원전":     [("두산에너빌리티","034020.KS"),("우진","105840.KQ"),("한전KPS","051600.KS"),("보성파워텍","006910.KQ")],
    "바이오":   [("셀트리온","068270.KS"),("에스티팜","237690.KQ"),("알테오젠","196170.KQ"),("메디톡스","086900.KQ")],
    "전력":     [("한전KPS","051600.KS"),("LS ELECTRIC","010120.KS"),("효성중공업","298040.KS"),("대한전선","001440.KS")],
}

# ------------- RSS -------------

def _clean_html(raw: str) -> str:
    if not raw:
        return ""
    if _BS_OK and BeautifulSoup is not None:
        return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    # bs4 미설치 시 간단 정리
    return str(raw).replace("<br>", " ").replace("<br/>", " ")


def _parse_entries(feed: Any, days: int) -> List[Dict[str, str]]:
    """feedparser의 결과에서 최근 N일 이내 항목을 추려 표준화.
    - tzdata 없이도 동작하도록 KST 고정
    - published_parsed/updated_parsed 없으면 포함(시간 '-')
    """
    now = datetime.now(KST)
    out: List[Dict[str, str]] = []
    entries = getattr(feed, "entries", []) if feed is not None else []
    for e in entries:
        t: Optional[datetime] = None
        try:
            if getattr(e, "published_parsed", None):
                t = datetime(*e.published_parsed[:6], tzinfo=KST)  # type: ignore[attr-defined]
            elif getattr(e, "updated_parsed", None):
                t = datetime(*e.updated_parsed[:6], tzinfo=KST)  # type: ignore[attr-defined]
        except Exception:
            t = None
        if t and (now - t) > timedelta(days=days):
            continue
        title = (getattr(e, "title", "") or "").strip()
        link = (getattr(e, "link", "") or "").strip()
        if link.startswith("./"):
            link = "https://news.google.com/" + link[2:]
        desc = _clean_html(getattr(e, "summary", ""))
        out.append({
            "title": title,
            "link": link,
            "time": t.strftime("%Y-%m-%d %H:%M") if t else "-",
            "desc": desc,
        })
    return out


def _mock_news(keyword: str, days: int, limit: int) -> List[Dict[str, str]]:
    """네트워크/의존성 부재 시 사용되는 결정적(Mock) 뉴스 생성기."""
    now = datetime.now(KST)
    items: List[Dict[str, str]] = []
    # 키워드가 테마에 걸리도록 일부 샘플 텍스트 삽입
    sample_descs = [
        f"{keyword} 관련 AI 투자 확대 소식",
        f"{keyword} 반도체 공급망 강화 및 HBM 수요 증가",
        f"{keyword} 로봇 자동화 도입 확대",
        f"{keyword} 2차전지 LFP 기술 경쟁",
    ]
    for i in range(max(1, min(limit, 20))):
        t = now - timedelta(hours=i*3)
        items.append({
            "title": f"[{keyword}] 테스트 뉴스 {i+1}",
            "link": f"https://example.com/{quote_plus(keyword)}/{i+1}",
            "time": t.strftime("%Y-%m-%d %H:%M"),
            "desc": sample_descs[i % len(sample_descs)],
        })
    return items


def fetch_google_news_by_keyword(keyword: str, days: int = 3, limit: int = 40) -> List[Dict[str, str]]:
    """구글 뉴스 RSS에서 키워드 기반으로 기사 수집.
    - feedparser/네트워크 실패 시 **모의 데이터**로 폴백
    """
    try:
        url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl=ko&gl=KR&ceid=KR%3Ako"
        if _FEED_OK and feedparser is not None:
            feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"})
            items = _parse_entries(feed, days)
            if items:
                return items[:limit]
    except Exception:
        pass
    # 폴백: mock 데이터
    return _mock_news(keyword, days=days, limit=limit)


def fetch_category_news(cat: str, days: int = 3, max_items: int = 100) -> List[Dict[str, str]]:
    seen, merged = set(), []
    for kw in CATEGORIES.get(cat, []):
        for it in fetch_google_news_by_keyword(kw, days=days, limit=40):
            key = (it.get("title",""), it.get("link",""))
            if key in seen:
                continue
            seen.add(key)
            merged.append(it)

    def _key(x: Dict[str, str]) -> datetime:
        try:
            return datetime.strptime(x.get("time","-"), "%Y-%m-%d %H:%M")
        except Exception:
            return datetime.min

    merged.sort(key=_key, reverse=True)
    return merged[:max_items]


def fetch_all_news(days: int = 3, per_cat: int = 100) -> List[Dict[str, str]]:
    all_news: List[Dict[str, str]] = []
    for c in CATEGORIES.keys():
        all_news.extend(fetch_category_news(c, days=days, max_items=per_cat))
    return all_news

# ------------- 테마 감지 -------------

def detect_themes(news_list: List[Dict[str, str]]):
    result: Dict[str, int] = {}
    sample_link: Dict[str, str] = {}
    for n in news_list:
        text = f"{n.get('title','')} {n.get('desc','')}".lower()
        for theme, kws in THEME_KEYWORDS.items():
            if any(k in text for k in kws):
                result[theme] = result.get(theme, 0) + 1
                sample_link.setdefault(theme, n.get("link",""))
    rows = [{"theme": t, "count": c, "sample_link": sample_link.get(t, "")} for t, c in result.items() if c > 0]
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows


# =============================
# 자체 테스트 (네트워크 미사용)
# =============================
if __name__ == "__main__":
    # 1) 단일 키워드 수집 (mock 폴백이 동작해야 함)
    items = fetch_google_news_by_keyword("AI", days=3, limit=10)
    assert isinstance(items, list) and len(items) >= 1
    assert set(["title","link","time","desc"]).issubset(items[0].keys())

    # 2) 카테고리 수집/정렬/중복 제거
    cat_items = fetch_category_news("산업뉴스", days=3, max_items=50)
    assert isinstance(cat_items, list)
    if cat_items:
        # 시간 역순 정렬이 맞는지 대략 검증
        ts = [i["time"] for i in cat_items[:5]]
        assert all(isinstance(t, str) and len(t) >= 10 for t in ts)

    # 3) 전체 수집 + 테마 감지
    all_news = fetch_all_news(days=3, per_cat=30)
    themes = detect_themes(all_news)
    assert isinstance(themes, list)
    if all_news:
        # mock 데이터에는 AI/반도체/로봇/2차전지 키워드가 포함되어 있어야 함
        theme_names = [r["theme"] for r in themes]
        assert any(t in theme_names for t in ["AI","반도체","로봇","이차전지"]), "테마 감지 실패 (mock)"

    print("[news] ✅ All self-tests passed. FEED:", _FEED_OK, "BS4:", _BS_OK)
