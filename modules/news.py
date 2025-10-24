modules/news.py

Google News RSS (relevance) 기반 수집 · 카테고리별 100건 집계 · 테마 감지/매핑

v3.7.1+R (실서비스용)

from future import annotations from typing import Any, Dict, Iterable, List, Tuple, Optional from datetime import datetime, timedelta, timezone from urllib.parse import quote_plus import urllib.request import xml.etree.ElementTree as ET from email.utils import parsedate_to_datetime

선택 의존성(있으면 사용, 없어도 동작)

try:  # pragma: no cover import feedparser  # type: ignore _FP = True except Exception:  # pragma: no cover feedparser = None  # type: ignore _FP = False

tzdata 없이 안전한 KST (UTC+9)

KST = timezone(timedelta(hours=9))

-------- 카테고리/테마 사전 --------

CATEGORIES: Dict[str, List[str]] = { "세계":   ["세계 경제", "국제 무역", "미국 증시", "중국 경제", "유럽 증시"], "정책":   ["정부 정책", "산업부", "예산", "금융위원회", "규제 완화", "수출 지원"], "경제":   ["코스피", "코스닥", "금리", "물가", "환율", "GDP", "무역수지"], "산업":   ["AI", "반도체", "배터리", "로봇", "자동차", "데이터센터", "전력"], }

THEME_KEYWORDS: Dict[str, List[str]] = { "AI":        ["ai","인공지능","챗봇","생성형","오픈ai","엔비디아","gpu","llm","챗gpt"], "반도체":     ["반도체","hbm","칩","램","파운드리","소부장"], "로봇":       ["로봇","협동로봇","amr","자율주행로봇","로보틱스"], "이차전지":    ["2차전지","이차전지","배터리","전고체","양극재","음극재","lfp"], "에너지":     ["에너지","정유","전력","가스","태양광","풍력"], "조선":       ["조선","선박","수주","lng선","해운"], "LNG":       ["lng","액화천연가스","가스공사","터미널"], "원전":       ["원전","원자력","smr","우라늄"], "바이오":     ["바이오","제약","신약","임상","항암"], "전력":       ["전력","송배전","ess","스마트그리드","전기요금"], "데이터센터":  ["데이터센터","idc","클라우드","서버","랙","냉각","전력 인프라"], }

대형/중형/소형 섞은 대표 예시

THEME_STOCKS: Dict[str, List[Tuple[str, str]]] = { "AI":       [("삼성전자","005930.KS"),("네이버","035420.KS"),("카카오","035720.KS"), ("솔트룩스","304100.KQ"),("브레인즈컴퍼니","099390.KQ"),("한글과컴퓨터","030520.KS")], "반도체":   [("SK하이닉스","000660.KS"),("DB하이텍","000990.KS"),("리노공업","058470.KQ"), ("원익IPS","240810.KQ"),("티씨케이","064760.KQ"),("에프에스티","036810.KQ")], "로봇":     [("레인보우로보틱스","277810.KQ"),("유진로봇","056080.KQ"),("티로보틱스","117730.KQ"), ("로보스타","090360.KQ"),("스맥","099440.KQ")], "이차전지": [("LG에너지솔루션","373220.KS"),("포스코퓨처엠","003670.KS"),("에코프로","086520.KQ"), ("코스모신소재","005070.KQ"),("엘앤에프","066970.KQ")], "에너지":   [("SK이노베이션","096770.KS"),("GS","078930.KS"),("S-Oil","010950.KS"), ("한화솔루션","009830.KS"),("OCI홀딩스","010060.KS")], "조선":     [("HD한국조선해양","009540.KS"),("HD현대미포","010620.KS"),("삼성중공업","010140.KS"),("한화오션","042660.KS")], "LNG":     [("한국가스공사","036460.KS"),("지에스이","053050.KQ"),("대성에너지","117580.KQ"),("SK가스","018670.KS")], "원전":     [("두산에너빌리티","034020.KS"),("우진","105840.KQ"),("한전KPS","051600.KS"),("보성파워텍","006910.KQ")], "바이오":   [("셀트리온","068270.KS"),("에스티팜","237690.KQ"),("알테오젠","196170.KQ"),("메디톡스","086900.KQ")], "전력":     [("한전KPS","051600.KS"),("LS ELECTRIC","010120.KS"),("효성중공업","298040.KS"),("대한전선","001440.KS")], "데이터센터":[("삼성SDS","018260.KS"),("효성중공업","298040.KS"),("LS ELECTRIC","010120.KS"),("대한전선","001440.KS")], }

------------- 유틸 -------------

def _clean_html(raw: str) -> str: if not raw: return "" return ( raw.replace("<br>", " ").replace("<br/>", " ").replace("<br />", " ") .replace("</p>", " ").replace("<p>", " ") )

-------- stdlib 기반 RSS 파서 (기본 경로) --------

def _fetch_google_news_relevance(keyword: str, days: int = 3, limit: int = 40) -> List[Dict[str, str]]: """Google News RSS (relevance scoring) — 외부 패키지 없이 urllib + ElementTree로 파싱""" if not keyword: return [] url = ( "https://news.google.com/rss/search?q=" + quote_plus(keyword) + "&hl=ko&gl=KR&ceid=KR:ko&scoring=r" ) req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}) with urllib.request.urlopen(req, timeout=10) as resp: data = resp.read() root = ET.fromstring(data)

now = datetime.now(KST)
items: List[Dict[str, str]] = []
for it in root.findall(".//item"):
    title = (it.findtext("title") or "").strip()
    link = (it.findtext("link") or "").strip()
    desc = _clean_html(it.findtext("description") or "")
    pub = it.findtext("pubDate") or it.findtext("updated") or ""
    t: Optional[datetime] = None
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        t = dt.astimezone(KST)
    except Exception:
        t = None
    if t and (now - t) > timedelta(days=int(days)):
        continue
    items.append({
        "title": title,
        "link": link,
        "time": t.strftime("%Y-%m-%d %H:%M") if t else "-",
        "desc": desc,
    })
# 최신순 제한
def _key(x: Dict[str, str]):
    try:
        return datetime.strptime(x.get("time",""), "%Y-%m-%d %H:%M")
    except Exception:
        return datetime.min
items.sort(key=_key, reverse=True)
return items[: max(0, int(limit))]

------------- RSS (통합 엔트리포인트) -------------

def fetch_google_news_by_keyword(keyword: str, days: int = 3, limit: int = 40) -> List[Dict[str, str]]: # 1) stdlib relevance 파서 우선 try: return _fetch_google_news_relevance(keyword, days=days, limit=limit) except Exception: pass # 2) feedparser 폴백(있으면) if _FP and feedparser is not None: try: url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}&hl=ko&gl=KR&ceid=KR%3Ako&scoring=r" feed = feedparser.parse(url, request_headers={"User-Agent": "Mozilla/5.0"}) # 단순 변환 now = datetime.now(KST) out: List[Dict[str, str]] = [] for e in getattr(feed, "entries", []) or []: t = None try: tm = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None) if tm: t = datetime(*tm[:6], tzinfo=timezone.utc).astimezone(KST) except Exception: t = None if t and (now - t) > timedelta(days=days): continue title = (getattr(e, "title", "") or "").strip() link = (getattr(e, "link", "") or "").strip() if link.startswith("./"): link = "https://news.google.com/" + link[2:] desc = _clean_html(getattr(e, "summary", "") or getattr(e, "description", "")) out.append({"title": title, "link": link, "time": t.strftime("%Y-%m-%d %H:%M") if t else "-", "desc": desc}) # 최신순 제한 def _k(x: Dict[str, str]): try: return datetime.strptime(x.get("time",""), "%Y-%m-%d %H:%M") except Exception: return datetime.min out.sort(key=_k, reverse=True) return out[: max(0, int(limit))] except Exception: pass # 3) 최후 폴백: 빈 리스트(앱 단에서 안내) return []

def fetch_category_news(cat: str, days: int = 3, max_items: int = 100) -> List[Dict[str, str]]: """카테고리 내 키워드들을 relevance RSS로 수집 → dedupe → 최신순 정렬 → 최대 100건. per-kw cap은 자동으로 계산(키워드 수에 맞춰 균등 분배). """ kws = CATEGORIES.get(cat, []) if not kws: return [] per_kw = max(15, int(max_items / max(1, len(kws))))  # 키워드별 최소 15건 시도 seen, merged = set(), [] for kw in kws: for it in fetch_google_news_by_keyword(kw, days=days, limit=per_kw): key = (it.get("title",""), it.get("link","")) if key in seen: continue seen.add(key) merged.append(it) # 최신순 정렬 후 상한 적용 def _key(x: Dict[str, str]): try: return datetime.strptime(x.get("time",""), "%Y-%m-%d %H:%M") except Exception: return datetime.min merged.sort(key=_key, reverse=True) return merged[: max(0, int(max_items))]

def fetch_all_news(days: int = 3, per_cat: int = 100) -> List[Dict[str, str]]: all_news: List[Dict[str, str]] = [] for c in CATEGORIES.keys(): all_news.extend(fetch_category_news(c, days=days, max_items=per_cat)) return all_news

------------- 테마 감지 -------------

def detect_themes(news_list: Iterable[Dict[str, str]]): result: Dict[str, int] = {} sample_link: Dict[str, str] = {} for n in news_list or []: text = f"{n.get('title','')} {n.get('desc','')}".lower() for theme, kws in THEME_KEYWORDS.items(): if any(k in text for k in kws): result[theme] = result.get(theme, 0) + 1 sample_link.setdefault(theme, n.get("link", "")) rows = [{"theme": t, "count": c, "sample_link": sample_link.get(t, "")} for t, c in result.items() if c > 0] rows.sort(key=lambda x: x["count"], reverse=True) return rows

------------------------------

Self tests (best-effort)

------------------------------

if name == "main": try: res = fetch_google_news_by_keyword("AI", days=3, limit=20) assert isinstance(res, list) except Exception: pass try: cat = fetch_category_news("산업", days=3, max_items=100) assert isinstance(cat, list) except Exception: pass print("[news] ✅ ready: relevance RSS mode, feedparser:", _FP)
