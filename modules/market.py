# (기존 modules/market.py 안) --- HTTP 폴백 부분 교체 ---

import requests
from urllib.parse import quote

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

def _http_json(url: str, timeout: int = 6) -> dict:
    r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
    r.raise_for_status()
    return r.json()

# 1) Quote API (정규장 기준 값) ----------------------------
from functools import lru_cache
import time
_mem_cache = {}

@lru_cache(maxsize=256)
def _fetch_yahoo_quote_once(symbol: str):
    enc = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={enc}"
    try:
        j = _http_json(url)
        res = (j.get("quoteResponse", {}) or {}).get("result", [])
        if not res:
            return None, None, None
        q = res[0]
        # 기본은 정규장 값
        last = q.get("regularMarketPrice")
        prev = q.get("regularMarketPreviousClose")
        vol  = q.get("regularMarketVolume")
        # 장마감 후(post) 가격이 있으면 선택적으로 반영 (원하면 주석 해제)
        # if q.get("marketState") in ("POST", "POSTPOST") and q.get("postMarketPrice"):
        #     last = q.get("postMarketPrice")
        if last is None or prev is None:
            return None, None, None
        return float(last), float(prev), (int(vol) if isinstance(vol, (int, float)) else None)
    except Exception:
        return None, None, None

# 2) Chart API (최후의 수단) -------------------------------
@lru_cache(maxsize=256)
def _fetch_yahoo_chart_once(symbol: str):
    enc = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?range=5d&interval=1d&includePrePost=false"
    try:
        j = _http_json(url)
        res = j.get("chart", {}).get("result", [])
        if not res:
            return None, None, None
        r0 = res[0]
        closes = (r0.get("indicators", {}).get("quote", [{}])[0].get("close") or [])
        vols   = (r0.get("indicators", {}).get("quote", [{}])[0].get("volume") or [])
        closes = [c for c in closes if isinstance(c, (int, float))]
        if len(closes) < 2:
            return None, None, None
        last = float(closes[-1]); prev = float(closes[-2])
        vol  = int(vols[-1]) if vols and isinstance(vols[-1], (int, float)) else None
        return last, prev, vol
    except Exception:
        return None, None, None

# 짧은 TTL 메모리 캐시
def _memo(fn, symbol: str, ttl: float = 3.0):
    now = time.time()
    k = (fn.__name__, symbol)
    v = _mem_cache.get(k)
    if v and (now - v[0]) < ttl:
        return v[1]
    data = fn(symbol)
    _mem_cache[k] = (now, data)
    return data

def fetch_quote(ticker: str):
    """
    (last, prev, volume)
    1) yfinance fast_info/history
    2) Yahoo Quote API  ← 종가/등락률 정확도 우선
    3) Yahoo Chart API  ← 최후의 수단
    """
    # 1) yfinance 우선
    if _YF:
        try:
            t = yf.Ticker(ticker)
            fi = getattr(t, "fast_info", None)
            if fi:
                last = getattr(fi, "last_price", None)
                prev = getattr(fi, "previous_close", None)
                vol  = getattr(fi, "last_volume", None)
                if last and prev:
                    return float(last), float(prev), (int(vol) if vol else None)
        except Exception:
            pass
        try:
            df = yf.Ticker(ticker).history(period="10d", interval="1d", auto_adjust=True)
            if df is not None and not df.empty:
                closes = df["Close"].dropna()
                vols = df.get("Volume")
                if len(closes) >= 2:
                    last = float(closes.iloc[-1]); prev = float(closes.iloc[-2])
                    vol = None
                    if vols is not None and not np.isnan(vols.iloc[-1]):
                        vol = int(vols.iloc[-1])
                    return last, prev, vol
        except Exception:
            pass

    # 2) Quote API
    q = _memo(_fetch_yahoo_quote_once, ticker)
    if q != (None, None, None):
        return q

    # 3) Chart API
    return _memo(_fetch_yahoo_chart_once, ticker)
