# -*- coding: utf-8 -*-
"""
구글뉴스 RSS 기반으로 대시보드 데이터 생성
- headlines_top10.json  : 최신 헤드라인 10개
- news_100.json         : 분석용 원시 뉴스 100개
- theme_top5.json       : 뉴스 빈도로 뽑은 Top5 테마(+대표종목 텍스트)
- theme_secondary5.json : 전체 테마 집계(감쇠 점수 포함)
- keyword_map_month.json: 최근 뉴스의 키워드 카운트(간단히 제목 기반)
- new_themes.json       : 신규(미지정) 바이그램 후보
"""
import os, json, re, time
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

import feedparser

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# --------- 1) 테마-키워드/종목 매핑 (필요 시 자유롭게 추가) ----------
THEME_MAP = {
  "AI": {"keywords":["ai","인공지능","gpt","코파일럿","오픈ai","생성형"], 
         "stocks":["삼성전자","네이버","카카오","더존비즈온","티맥스소프트"]},
  "반도체":{"keywords":["반도체","메모리","hbm","파운드리","d램","낸드","첨단패키징","후공정"],
            "stocks":["삼성전자","SK하이닉스","DB하이텍","한미반도체","테스"]},
  "로봇":{"keywords":["로봇","협동로봇","서비스로봇","지능형로봇"],
          "stocks":["레인보우로보틱스","현대로보틱스","유진로봇","티로보틱스","로보스타"]},
  "이차전지":{"keywords":["이차전지","2차전지","양극재","음극재","전고체","배터리","lfg","ncm","nca"],
            "stocks":["LG에너지솔루션","포스코퓨처엠","에코프로","에코프로비엠","엘앤에프"]},
  "에너지":{"keywords":["에너지","정유","전력","전기요금","lng발전"],
          "stocks":["한국전력","두산에너빌리티","GS","SK이노베이션","한국가스공사"]},
  "조선":{"keywords":["조선","수주","컨테이너선","lng선","해양플랜트"],
         "stocks":["HD한국조선해양","HD현대미포","삼성중공업","한화오션","HSD엔진"]},
  "LNG":{"keywords":["lng","액화천연가스","가스","터미널"],
        "stocks":["한국가스공사","지에스이","대성에너지","포스코인터내셔널","SK가스"]},
  "원전":{"keywords":["원전","원자력","smr","경수로"],
         "stocks":["두산에너빌리티","우진","한전KPS","한전기술","일진파워"]},
  "바이오":{"keywords":["바이오","신약","임상","항암","mRNA","바이오시밀러"],
          "stocks":["삼성바이오로직스","셀트리온","HLB","에스티팜","메디톡스"]},
}

# --------- 2) 구글뉴스 RSS 쿼리 정의 ----------
RSS_QUERIES = [
    "경제", "정책", "산업", "리포트 OR 보고서 OR 애널리스트"
]
BASE = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

def fetch_feed(query, limit=40):
    url = BASE.format(q=query)
    d = feedparser.parse(url)
    items = []
    for e in d.entries[:limit]:
        title = e.title
        link = getattr(e, "link", None)
        pub = getattr(e, "published", None)
        items.append({"title": title, "link": link, "published": pub})
    return items

# --------- 3) 뉴스 수집 ----------
news = []
for q in RSS_QUERIES:
    news.extend(fetch_feed(q, limit=40))

# 중복 제거(링크 기준)
seen = set()
dedup = []
for n in news:
    k = (n.get("link") or n.get("title"))
    if k and k not in seen:
        dedup.append(n); seen.add(k)

# 최신 100개
news_100 = dedup[:100]

# 상단 노출 10개 (그대로)
headlines_top10 = news_100[:10]

# --------- 4) 테마 분석 ----------
def norm(s:str)->str:
    return re.sub(r"[^0-9A-Za-z가-힣]", " ", (s or "")).lower()

theme_scores = defaultdict(int)
theme_samples = defaultdict(list)
keyword_counter = Counter()

for n in news_100:
    title = n.get("title","")
    t_norm = norm(title)
    # 키워드 카운트(월간 키워드맵 용도)
    for theme, cfg in THEME_MAP.items():
        for kw in cfg["keywords"]:
            if kw.lower() in t_norm:
                keyword_counter[kw] += 1

    # 테마 점수
    for theme, cfg in THEME_MAP.items():
        hit = False
        for kw in cfg["keywords"]:
            if kw.lower() in t_norm:
                theme_scores[theme] += 1
                hit = True
        if hit and len(theme_samples[theme])<1 and n.get("link"):
            theme_samples[theme].append(n["link"])

# Top5
top5 = sorted(
    [{"theme":t, "count":c, "score":c, 
      "rep_stocks":", ".join(THEME_MAP[t]["stocks"]),
      "sample_link": theme_samples[t][0] if theme_samples[t] else ""} 
     for t,c in theme_scores.items()],
    key=lambda x:(x["score"], x["count"]), reverse=True
)[:5]

# 전체(감쇠 스코어: 최근 100건에 동일 가중)
secondary = sorted(
    [{"theme":t, "count":c, "score":c, 
      "sample_link": theme_samples[t][0] if theme_samples[t] else ""} 
     for t,c in theme_scores.items()],
    key=lambda x:(x["score"], x["count"]), reverse=True
)

# 신규 테마 후보(테마맵에 없는 단어 조합 간단 탐색)
# 너무 과한 연산은 피하고, 뉴스 제목 bigram에서 3회 이상 등장하는 것만 추출
from itertools import pairwise
bigram = Counter()
for n in news_100:
    toks = [w for w in norm(n.get("title","")).split() if len(w)>=2]
    for a,b in pairwise(toks):
        pair = f"{a} {b}"
        if not any(pair.find(k) >= 0 for cfg in THEME_MAP.values() for k in cfg["keywords"]):
            bigram[pair]+=1
new_candidates = [p for p,c in bigram.most_common(30) if c>=3]

# --------- 5) 저장 ----------
def dump(path, obj):
    with open(os.path.join(DATA_DIR, path), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# 헤드라인/뉴스
dump("headlines_top10.json", {"items": headlines_top10})
dump("news_100.json", {"items": news_100})

# 테마
dump("theme_top5.json", {"themes": top5})
dump("theme_secondary5.json", {"themes": secondary})

# 키워드맵(상위 30)
kw30 = [{"keyword":k, "count":v} for k,v in keyword_counter.most_common(30)]
dump("keyword_map_month.json", {"keywords": kw30})

# 신규 테마
dump("new_themes.json", new_candidates)

print(f"[OK] news={len(news_100)} top5={len(top5)} kw={len(kw30)} new={len(new_candidates)}")
