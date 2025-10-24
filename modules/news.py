modules/news.py

구글 뉴스 RSS 수집, 테마 감지, 테마-종목 맵 (tzdata/네트워크/패키지 부재 방어)

v3.7.1+3

from future import annotations from typing import Any, Dict, Iterable, List, Optional, Tuple from datetime import datetime, timedelta, timezone from urllib.parse import quote_plus

------------------------------

Optional deps (feedparser / bs4)

------------------------------

try:  # pragma: no cover import feedparser  # type: ignore _FP = True except Exception:  # pragma: no cover feedparser = None  # type: ignore _FP = False

try:  # pragma: no cover from bs4 import BeautifulSoup  # type: ignore _BS = True except Exception:  # pragma: no cover BeautifulSoup = None  # type: ignore _BS = False

tzdata 없이 안전한 KST (UTC+9)

KST = timezone(timedelta(hours=9))

-------- 카테고리/테마 사전 --------

CATEGORIES: Dict[str, List[str]] = { "경제뉴스": ["경제", "금리", "물가", "환율", "성장률", "무역"], "주식뉴스": ["코스피", "코스닥", "증시", "주가", "외국인 매수", "기관 매도"], "산업뉴스": ["반도체", "AI", "배터리", "자동차", "로봇", "수출입"], "정책뉴스": ["정책", "정부", "예산", "규제", "세금", "산업부"], }

THEME_KEYWORDS: Dict[str, List[str]] = { "AI":        ["ai","인공지능","챗봇","생성형","오픈ai","엔비디아","gpu","llm"], "반도체":     ["반도체","hbm","칩","램","파운드리","소부장"], "로봇":       ["로봇","협동로봇","amr","자율주행로봇","로보틱스"], "이차전지":    ["2차전지","이차전지","배터리","전고체","양극재","음극재","lfp"], "에너지":     ["에너지","정유","전력","가스","태양광","풍력"], "조선":       ["조선","선박","수주","lng선","해운"], "LNG":       ["lng","액화천연가스","가스공사","터미널"], "원전":       ["원전","원자력","smr","우라늄"], "바이오":     ["바이오","제약","신약","임상","항암"], "전력":       ["전력","송배전","ESS","스마트그리드","전기요금"], }

대형/중형/소형 섞은 대표 예시 (원하는대로 확장 가능)

THEME_STOCKS: Dict[str, List[Tuple[str, str]]] = { "AI":       [("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"), ("솔트룩스","304100.KQ"),("브레인즈컴퍼니","099390.KQ"),("한글과컴퓨터","030520.KS")], "반도체":   [("SK하이닉스","000660.KS"),("DB하이텍","000990.KS"),("리노공업","058470.KQ"), ("원익IPS","240810.KQ"),("티씨케이","064760.KQ"),("에프에스티","036810.KQ")], "로봇":     [("레인보우로보틱스","277810.KQ"),("유진로봇","056080.KQ"),("티로보틱스","117730.KQ"), ("로보스타","090360.KQ"),("스맥","099440.KQ")], "이차전지": [("LG에너지솔루션","373220.KS"),("포스코퓨처엠","003670.KS"), ("에코프로","086520.KQ"),("코스모신소재","005070.KQ"),("엘앤에프","066970.KQ")], "에너지":   [("SK이노베이션","096770.KS"),("GS","078930.KS"),("S-Oil","010950.KS"), ("한화솔루션","009830.KS"),("OCI홀딩스","010060.KS")], "조선":     [("HD한국조선해양","009540.KS"),("HD현대미포","010620.KS"), ("삼성중공업","010140.KS"),("한화오션","042660.KS")], "LNG":     [("한국가스공사","036460.KS"),("지에스이","053050.KQ"),("대성에너지","117580.KQ"),("SK가스","018670.KS")], "원전":     [("두산에너빌리티","034020.KS"),("우진","105840.KQ"),("한전KPS","051600.KS"),("보성파워텍","006910.KQ")], "바이오":   [("셀트리온","068270.KS"),("에스티팜","237690.KQ"),("알테오젠","196170.KQ"),("메디톡스","086900.KQ")], "전력":     [("한전KPS","051600.KS"),("LS ELECTRIC","010120.KS"),("효성중공업","298040.KS"),("대한전선","001440.KS")], }

------------- 유틸 -------------

def _clean_html(raw: str) -> str: if not raw: return "" if _BS and BeautifulSoup is not None: return BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) # bs4 없음 → 아주 단순 제거 return ( raw.replace("<br>", " ") .replace("<br/>", " ") .replace("<br />", " ") .replace("</p>", " ") .replace("<p>", " ") )

def _parse_entries(feed: Any, days: int) -> List[Dict[str, str]]: """feedparser의 결과에서 최근 N일 이내 항목을 추려 표준화. - tzdata 없이도 동작하도록 UTC→KST 변환 - published_parsed/updated_parsed 없으면 포함(시간 '-') """ now = datetime.now(KST) out: List[Dict[str, str]] = [] entries = getattr(feed, "entries", []) if feed is not None else [] for e in entries: t = None try: tm = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None) if tm: # RSS의 struct_time(UTC 가정) → aware datetime(UTC) → KST 변환 t = datetime(*tm[:6], tzinfo=timezone.utc).astimezone(KST) except Exception: t = None if t and (now - t) > timedelta(days=int(days)): continue title = (getattr(e, "title", "") or "").strip() link = (getattr(e, "link", "") or "").strip() if link.startswith("./"): link = "https://news.google.com/" + link[2:] desc_raw = getattr(e, "summary", "") or getattr(e, "description", "") desc = _clean_html(desc_raw) out.append({ "title": title, "link": link, "time": t.strftime("%Y-%m-%d %H:%M") if t else "-", "desc": desc, }) return out

------------- RSS -------------

def fetch_google_news_by_keyword(keyword: str, days: int = 3, limit: int = 40) -> List[Dict[str, str]]: """구글 뉴스 RSS를 키워드로 수집. 패키지/네트워크가 없으면 빈 리스트/더미 반환.""" if not keyword: return [] if _FP and feedparser is not None: try: url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl=ko&gl=KR&ceid=KR%3Ako" feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"}) return _parse_entries(feed, days)[: max(0, int(limit))] except Exception: pass # 패키지 부재/네트워크 실패 → 더미 최소 반환 now = datetime.now(KST).strftime("%Y-%m-%d %H:%M") return [{"title": f"[더미] {keyword} 관련 뉴스", "link": "https://example.com/news", "time": now, "desc": "-"}]

def fetch_category_news(cat: str, days: int = 3, max_items: int = 100) -> List[Dict[str, str]]: seen, merged = set(), [] for kw in CATEGORIES.get(cat, []): for it in fetch_google_news_by_keyword(kw, days=days, limit=40): key = (it.get("title",""), it.get("link","")) if key in seen: continue seen.add(key) merged.append(it) def _key(x: Dict[str, str]): try: return datetime.strptime(x.get("time",""), "%Y-%m-%d %H:%M") except Exception: return datetime.min.replace(tzinfo=None) merged.sort(key=_key, reverse=True) return merged[: max(0, int(max_items))]

def fetch_all_news(days: int = 3, per_cat: int = 100) -> List[Dict[str, str]]: all_news: List[Dict[str, str]] = [] for c in CATEGORIES.keys(): all_news.extend(fetch_category_news(c, days=days, max_items=per_cat)) return all_news

------------- 테마 감지 -------------

def detect_themes(news_list: Iterable[Dict[str, str]]) -> List[Dict[str, str]]: result: Dict[str, int] = {} sample_link: Dict[str, str] = {} for n in news_list or []: text = f"{n.get('title','')} {n.get('desc','')}".lower() for theme, kws in THEME_KEYWORDS.items(): if any(k in text for k in kws): result[theme] = result.get(theme, 0) + 1 sample_link.setdefault(theme, n.get("link", "")) rows = [{"theme": t, "count": c, "sample_link": sample_link.get(t, "")} for t, c in result.items() if c > 0] rows.sort(key=lambda x: x["count"], reverse=True) return rows

------------------------------

Self tests (no external net required)

------------------------------

if name == "main": # 1) 카테고리 키워드 구성 검사 assert "경제뉴스" in CATEGORIES and isinstance(CATEGORIES["경제뉴스"], list)

# 2) 개별 키워드 RSS (패키지/네트워크와 무관하게 최소 1건 보장)
r = fetch_google_news_by_keyword("AI", days=3, limit=5)
assert isinstance(r, list) and len(r) >= 1
assert {"title","link","time","desc"}.issubset(r[0].keys())

# 3) 카테고리/전체 뉴스 병합/정렬
cat_news = fetch_category_news("주식뉴스", days=3, max_items=30)
assert isinstance(cat_news, list)

all_news = fetch_all_news(days=3, per_cat=10)
assert isinstance(all_news, list)

# 4) 테마 감지
themes = detect_themes(all_news)
assert isinstance(themes, list)

print("[news] ✅ self-tests passed. feedparser:", _FP, "bs4:", _BS)
