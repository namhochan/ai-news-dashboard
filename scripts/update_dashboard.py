# -*- coding: utf-8 -*-
import os, json, re, time
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict
from urllib.parse import quote_plus
import feedparser
from itertools import pairwise

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

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

# ✅ RSS URL 인코딩
RSS_QUERIES = ["경제", "정책", "산업", "리포트 OR 보고서 OR 애널리스트"]
BASE = "https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"

def fetch_feed(query, limit=40):
    url = BASE.format(q=quote_plus(query))  # <-- 여기 수정됨
    d = feedparser.parse(url)
    items = []
    for e in d.entries[:limit]:
        title = e.title
        link = getattr(e, "link", None)
        pub = getattr(e, "published", None)
        items.append({"title": title, "link": link, "published": pub})
    return items

news = []
for q in RSS_QUERIES:
    news.extend(fetch_feed(q, limit=40))

# 중복 제거
seen, dedup = set(), []
for n in news:
    k = (n.get("link") or n.get("title"))
    if k and k not in seen:
        dedup.append(n); seen.add(k)
news_100 = dedup[:100]
headlines_top10 = news_100[:10]

# 테마 스코어 계산
def norm(s:str)->str:
    return re.sub(r"[^0-9A-Za-z가-힣]", " ", (s or "")).lower()

theme_scores, theme_samples = defaultdict(int), defaultdict(list)
keyword_counter = Counter()

for n in news_100:
    title = n.get("title","")
    t_norm = norm(title)
    for theme, cfg in THEME_MAP.items():
        for kw in cfg["keywords"]:
            if kw.lower() in t_norm:
                keyword_counter[kw]+=1
                theme_scores[theme]+=1
                if len(theme_samples[theme])<1:
                    theme_samples[theme].append(n.get("link",""))

# Top5
top5 = sorted(
    [{"theme":t, "count":c, "score":c, 
      "rep_stocks":", ".join(THEME_MAP[t]["stocks"]),
      "sample_link": theme_samples[t][0] if theme_samples[t] else ""} 
     for t,c in theme_scores.items()],
    key=lambda x:(x["score"], x["count"]), reverse=True
)[:5]

# 전체 테마
secondary = sorted(
    [{"theme":t, "count":c, "score":c, 
      "sample_link": theme_samples[t][0] if theme_samples[t] else ""} 
     for t,c in theme_scores.items()],
    key=lambda x:(x["score"], x["count"]), reverse=True
)

# 신규 테마 bigram
bigram = Counter()
for n in news_100:
    toks = [w for w in norm(n.get("title","")).split() if len(w)>=2]
    for a,b in pairwise(toks):
        pair = f"{a} {b}"
        if not any(pair.find(k)>=0 for cfg in THEME_MAP.values() for k in cfg["keywords"]):
            bigram[pair]+=1
new_candidates = [p for p,c in bigram.most_common(30) if c>=3]

# 저장
def dump(path, obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, path), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

dump("headlines_top10.json", {"items": headlines_top10})
dump("news_100.json", {"items": news_100})
dump("theme_top5.json", {"themes": top5})
dump("theme_secondary5.json", {"themes": secondary})
dump("keyword_map_month.json", {"keywords":[{"keyword":k,"count":v} for k,v in keyword_counter.most_common(30)]})
dump("new_themes.json", new_candidates)

print(f"[OK] news={len(news_100)} top5={len(top5)} kw={len(keyword_counter)} new={len(new_candidates)}")
# scripts/fetch_market.py
import json, os, math, time
from datetime import datetime, timezone, timedelta

import pandas as pd
import yfinance as yf

KST = timezone(timedelta(hours=9))
OUT = "data/market_today.json"

# Yahoo 티커 매핑
TICKERS = {
    "KOSPI":   "^KS11",     # 코스피
    "KOSDAQ":  "^KQ11",     # 코스닥
    "USDKRW":  "KRW=X",     # 달러/원
    "WTI":     "CL=F",      # 서부텍사스유 선물
    "Gold":    "GC=F",      # 금 선물
    "Copper":  "HG=F",      # 구리 선물
}

def pct_change(cur, prev):
    try:
        if prev is None or prev == 0 or any(map(math.isnan, [cur, prev])):
            return None
        return (cur - prev) / prev * 100.0
    except Exception:
        return None

def last_two_prices(ticker):
    """최근 5영업일에서 마지막 2개 종가를 가져옴(결측/휴장 대비 여유)."""
    try:
        df = yf.download(ticker, period="10d", interval="1d", auto_adjust=False, progress=False)
        if df.empty:
            return None, None
        closes = df["Close"].dropna().tail(2).tolist()
        if len(closes) == 1:
            return float(closes[0]), None
        elif len(closes) >= 2:
            return float(closes[-1]), float(closes[-2])
    except Exception:
        pass
    return None, None

def main():
    os.makedirs("data", exist_ok=True)
    out = {}
    for name, ticker in TICKERS.items():
        cur, prev = last_two_prices(ticker)
        chg = pct_change(cur, prev) if (cur is not None and prev is not None) else None
        out[name] = {
            "value": None if cur is None else round(cur, 2),
            "prev":  None if prev is None else round(prev, 2),
            "change_pct": None if chg is None else round(chg, 2),
            "ticker": ticker,
            "asof": datetime.now(KST).isoformat()
        }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
