# scripts/fetch_market.py
import json, os, math
from datetime import datetime, timezone, timedelta
import yfinance as yf

KST = timezone(timedelta(hours=9))
OUT = "data/market_today.json"

TICKERS = {
    "KOSPI":  "^KS11",
    "KOSDAQ": "^KQ11",  # 비면 ^KOSDAQ로 교체 테스트
    "USDKRW":"KRW=X",
    "WTI":    "CL=F",
    "Gold":   "GC=F",
    "Copper": "HG=F",
}

def pct_change(cur, prev):
    try:
        if prev in (None, 0) or cur is None:
            return None
        return (cur - prev) / prev * 100.0
    except Exception:
        return None

def last_two_prices(ticker):
    try:
        df = yf.download(ticker, period="10d", interval="1d", progress=False)
        closes = df["Close"].dropna().tail(2).tolist()
        if len(closes) == 1:
            return float(closes[0]), None
        if len(closes) >= 2:
            return float(closes[-1]), float(closes[-2])
    except Exception:
        pass
    return None, None

def main():
    os.makedirs("data", exist_ok=True)
    out = {}
    for name, t in TICKERS.items():
        cur, prev = last_two_prices(t)
        chg = pct_change(cur, prev) if (cur is not None and prev is not None) else None
        out[name] = {
            "value": None if cur is None else round(cur, 2),
            "prev":  None if prev is None else round(prev, 2),
            "change_pct": None if chg is None else round(chg, 2),
            "ticker": t,
            "asof": datetime.now(KST).isoformat()
        }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
