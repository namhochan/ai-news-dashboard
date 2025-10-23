# scripts/update_dashboard.py
# -*- coding: utf-8 -*-

import os
import json
import time
import math
import pytz
import requests
from datetime import datetime, timedelta
from collections import Counter, defaultdict

# ===== 공통 경로/유틸 =====
ROOT = os.path.dirname(os.path.dirname(__file__))  # repo 루트
DATA_DIR = os.path.join(ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)

def load_json(path, default=None):
    try:
        with open(os.path.join(ROOT, path) if not os.path.isabs(path) else path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(path, obj):
    full = os.path.join(ROOT, path) if not os.path.isabs(path) else path
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

KST = pytz.timezone("Asia/Seoul")

# ====== (1) 시장 지표 수집 ======
def fetch_market_today():
    """
    KOSPI/KOSDAQ/USDKRW 등을 간단히 가져와 저장.
    실제 사용 중인 API가 있으면 그 로직을 사용하세요.
    """
    # --- 예시용(필요 시 기존 코드로 교체) ---
    kosdaq = None
    kospi  = None
    usdk   = None
    try:
        # KRX 요약(샘플 엔드포인트/로직은 각자 쓰시는 것으로 교체)
        r = requests.get("https://query1.finance.yahoo.com/v7/finance/quote?symbols=^KQ11,^KS11,KRW=X", timeout=10)
        q = r.json()["quoteResponse"]["result"]
        for it in q:
            sym = it.get("symbol")
            if sym == "^KS11":
                kospi = it.get("regularMarketPrice")
            elif sym == "^KQ11":
                kosdaq = it.get("regularMarketPrice")
            elif sym == "KRW=X":
                # USD/KRW는 야후에서는 KRW=X가 USDKRW 환율(원/달러)의 역수이므로
                # KRW=X 값이 0.0007 형태로 오면 1/값을 취함
                v = it.get("regularMarketPrice")
                if v and v < 1:
                    usdk = 1 / v
                else:
                    usdk = v
    except Exception as e:
        print("[market] fetch fail:", e)

    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    return {
        "updated_at": now_kst,
        "KOSPI": kospi,
        "KOSDAQ": kosdaq,
        "USDKRW": usdk,
        "memo": "원/달러 고평가"
    }

# ====== (2) 뉴스 수집 ======
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "")  # GitHub Actions secrets 에서 주입

def fetch_headlines(query, page_size=30, days=3):
    """
    NewsAPI 예시. 기존에 사용하던 뉴스 소스가 있다면 그 코드로 교체하세요.
    """
    if not NEWSAPI_KEY:
        print("[news] NEWSAPI_KEY not found; return empty")
        return []

    from_dt = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "ko",
        "from": from_dt,
        "pageSize": page_size,
        "sortBy": "publishedAt",
        "apiKey": NEWSAPI_KEY,
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        items = r.json().get("articles", [])
        res = []
        for a in items:
            title = (a.get("title") or "").strip()
            url   = a.get("url")
            if title and url:
                res.append({"title": title, "link": url})
        return res
    except Exception as e:
        print(f"[news] fail for {query}:", e)
        return []

# ====== (3) 테마 정의 ======
# 필요 시 기존 테마/키워드 구성을 그대로 유지하세요.
THEMES = [
    {"theme": "AI 반도체", "keywords": ["AI", "반도체", "HBM"], "stocks": ["삼성전자", "하이닉스", "엘비세미콘", "티씨케이"]},
    {"theme": "로봇/스마트팩토리", "keywords": ["로봇", "스마트팩토리"], "stocks": ["유진로봇", "휴림로봇", "한라캐스트"]},
    {"theme": "조선/해양플랜트", "keywords": ["조선", "LNG", "해양"], "stocks": ["HD현대중공업", "대우조선해양", "대한조선"]},
    {"theme": "원전/SMR", "keywords": ["원전", "SMR"], "stocks": ["두산에너빌리티", "보성파워텍", "한신기계"]},
    {"theme": "2차전지 리사이클링", "keywords": ["2차전지", "리사이클링"], "stocks": ["성일하이텍", "새빗켐", "에코프로"]},
]

# ====== (4) 테마 TOP5 계산 & 최근 헤드라인 ======
def build_theme_top5_and_headlines():
    """
    각 테마의 키워드로 최신 뉴스 수집 → 테마별 점수(빈도) → 상위5개 선정
    또한 '최근 헤드라인 Top10' 도 함께 구성해서 반환
    """
    theme_scores = []
    collected_all = []  # 전체 제목 모음(키워드맵용)

    for t in THEMES:
        q = " OR ".join(t["keywords"])
        news = fetch_headlines(q, page_size=30, days=3)
        score = len(news)
        theme_scores.append({
            "theme": t["theme"],
            "desc": f"{t['theme']} 관련 뉴스 빈도 상승. 핵심 키워드: {', '.join(t['keywords'])}.",
            "stocks": ", ".join(t["stocks"]),
            "score": score,
            "keywords": t["keywords"],
            "news": news[:10],  # 테마별로 10건 정도(앱에서 2건만 보여줘도 됨)
        })
        collected_all.extend([n["title"] for n in news])

    # 상위 5개
    theme_scores.sort(key=lambda x: x["score"], reverse=True)
    top5 = theme_scores[:5]

    # 최근 헤드라인 Top10 (모든 테마 뉴스 합쳐서 최신순 상위 10)
    # 여기서는 방금 수집한 리스트에서 제목만 가져왔으니, 상위 10개로 대체
    recent10 = []
    for t in theme_scores:
        for it in t["news"]:
            if len(recent10) < 10:
                recent10.append(it)
    # 혹시 부족하면 빈 리스트로 둠

    return top5, recent10, collected_all

# ====== (5) 월간 키워드맵 (고친 부분) ======
def build_keyword_map(all_headlines, base_keywords):
    """
    실제 제목에 등장한 키워드의 등장 '문서 빈도'를 세서 저장.
    - 한 제목에서 같은 키워드가 여러 번 나와도 1회로 처리.
    - 상위 20개 저장.
    """
    kw_counter = Counter()

    for title in all_headlines:
        hit = set()
        for kw in base_keywords:
            if kw and kw in title:
                hit.add(kw)
        for kw in hit:
            kw_counter[kw] += 1

    data = [{"keyword": k, "count": v} for k, v in kw_counter.most_common(20)]

    if not data:
        print("[keyword_map] no matches; keep previous or save empty")
        prev = load_json("data/keyword_map.json", [])
        data = prev if prev else []

    save_json("data/keyword_map.json", data)
    print(f"[keyword_map] saved {len(data)} items")

# ====== (6) 텔레그램 알림 (옵션) ======
def send_telegram(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": msg}, timeout=10)
    except Exception as e:
        print("[telegram] fail:", e)

# ====== (7) 메인 실행 ======
def main():
    # 1) 시장 저장
    market = fetch_market_today()
    save_json("data/market_today.json", market)
    print("[market] saved")

    # 2) 테마 TOP5 / 최근 헤드라인 / 전체제목
    theme_top5, recent10, all_titles = build_theme_top5_and_headlines()
    # Streamlit에서 쓰는 구조로 저장
    save_json("data/theme_top5.json", theme_top5)
    print("[theme_top5] saved", len(theme_top5))

    # 최근 헤드라인은 app에서 바로 리스트를 보여주게끔 theme_top5에 포함해도 되고,
    # 필요하면 별도 파일로 저장
    save_json("data/recent_headlines.json", recent10)
    print("[recent10] saved", len(recent10))

    # 3) 월간 키워드맵 (여기가 수정 핵심)
    #   - 테마명 + 테마 키워드 전체를 관심 키워드로 사용
    theme_names = [t["theme"] for t in THEMES]
    core_keywords = []
    for t in THEMES:
        core_keywords.extend(t["keywords"])
    base_keywords = list({*theme_names, *core_keywords})
    build_keyword_map(all_titles, base_keywords)

    # 4) 텔레그램 알림 (선택)
    try:
        msg = f"[AI 뉴스 대시보드] 업데이트 완료\n- 테마Top5: {', '.join([t['theme'] for t in theme_top5])}\n- 헤드라인 수: {len(recent10)}\n- 시장: KOSPI={market.get('KOSPI')}, KOSDAQ={market.get('KOSDAQ')}, USD/KRW={market.get('USDKRW')}"
        send_telegram(msg)
    except Exception as e:
        print("[telegram] skipped:", e)

if __name__ == "__main__":
    main()
