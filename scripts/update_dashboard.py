import os, json, argparse, requests
from datetime import datetime, timedelta, timezone
import yfinance as yf
from collections import Counter

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
KST = timezone(timedelta(hours=9))

def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def load_json(path, default=None):
    if not os.path.exists(path): return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def pct(a, b):
    try: return round((a-b)/b*100, 2)
    except: return None

def fetch_market():
    tickers = {"KOSPI": "^KS11", "KOSDAQ": "^KQ11", "USDKRW": "KRW=X"}
    result = {"updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")}
    for n,t in tickers.items():
        try:
            df = yf.Ticker(t).history(period="5d", interval="1d")
            last, prev = df["Close"].iloc[-1], df["Close"].iloc[-2]
            c = pct(last, prev)
            result[n] = {"value": round(last,2),"change_pct":c,"dir":"▲" if c>=0 else "▼"}
        except: result[n] = {"value":None,"change_pct":None,"dir":""}
    save_json(f"{DATA_DIR}/market_today.json", result)
    return result

KEYWORDS = ["AI","반도체","로봇","바이오","원전","수소","전기차","2차전지","조선","에너지"]

def fetch_headlines():
    api = os.getenv("NEWSAPI_KEY")
    items=[]
    if api:
        try:
            url=f"https://newsapi.org/v2/top-headlines?country=kr&pageSize=40&apiKey={api}"
            j=requests.get(url,timeout=15).json()
            for a in j.get("articles",[]):
                if a.get("title") and a.get("url"):
                    items.append({"title":a["title"],"url":a["url"]})
        except: pass
    if not items:
        items=load_json(f"{DATA_DIR}/recent_headlines.json",[])
    items=items[:20]
    save_json(f"{DATA_DIR}/recent_headlines.json",items)
    return items

def build_keyword_map(h):
    c=Counter()
    for i in h:
        for k in KEYWORDS:
            if k in i["title"]: c[k]+=1
    d=[{"keyword":k,"count":v} for k,v in c.most_common()]
    save_json(f"{DATA_DIR}/keyword_map.json",d)
    return d

def build_theme_top5(k):
    s=sorted(k,key=lambda x:x["count"],reverse=True)[:5]
    if not s: s=[{"theme":"AI 반도체","score":10}]
    save_json(f"{DATA_DIR}/theme_top5.json",s)
    return s

def build_summary(m,t,h):
    lines=["*🧠 AI 뉴스 대시보드 자동 업데이트*",
           f"🕒 {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} 기준"]
    for k in ["KOSPI","KOSDAQ","USDKRW"]:
        d=m.get(k,{})
        if d.get("value"):
            lines.append(f"{k}: {d['value']} ({d['dir']}{d['change_pct']}%)")
    if t: lines.append("🔥 주요테마: "+", ".join([x.get("theme",x.get("keyword")) for x in t]))
    if h: lines.append(f"📰 뉴스 {len(h)}건 반영")
    return "\n".join(lines)

def main(summary_only=False):
    if summary_only:
        m=load_json(f"{DATA_DIR}/market_today.json",{})
        h=load_json(f"{DATA_DIR}/recent_headlines.json",[])
        k=load_json(f"{DATA_DIR}/keyword_map.json",[])
        t=load_json(f"{DATA_DIR}/theme_top5.json",[])
    else:
        m=fetch_market()
        h=fetch_headlines()
        k=build_keyword_map(h)
        t=build_theme_top5(k)
    print(build_summary(m,t,h))

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--summary-only",action="store_true")
    a=p.parse_args()
    main(summary_only=a.summary_only)
