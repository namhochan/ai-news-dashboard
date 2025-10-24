# modules/market.py
# 안정형 시세 수집 유틸 + 티커바 데이터

from __future__ import annotations
import math
import numpy as np
import yfinance as yf

# 숫자 포맷 공용
def fmt_number(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def fmt_percent(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

def fetch_quote(ticker: str):
    """
    1) Ticker.fast_info (last_price / previous_close / last_volume)
    2) 실패 시 history(period=10d, 1d, auto_adjust=True)
    -> (last, prev, volume) 반환. 실패 시 (None, None, None)
    """
    # 1) fast_info 시도
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

    # 2) history() 폴백
    try:
        df = yf.Ticker(ticker).history(period="10d", interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return None, None, None
        closes = df["Close"].dropna()
        vols = df.get("Volume")
        if len(closes) < 2:
            return None, None, None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        vol = None
        if vols is not None:
            v = vols.iloc[-1]
            vol = int(v) if v == v else None  # NaN 체크
        return last, prev, vol
    except Exception:
        return None, None, None


def build_ticker_items():
    """상단 지수/원자재/환율 티커바 데이터."""
    rows = [
        ("KOSPI",   "^KS11", 2),
        ("KOSDAQ",  "^KQ11", 2),
        ("DOW",     "^DJI",  2),
        ("NASDAQ",  "^IXIC", 2),
        ("USD/KRW", "KRW=X", 2),
        ("WTI",     "CL=F",  2),
        ("Gold",    "GC=F",  2),
        ("Copper",  "HG=F",  3),
    ]
    items = []
    for (name, ticker, dp) in rows:
        last, prev, _ = fetch_quote(ticker)
        pct = None
        if last is not None and prev not in (None, 0):
            pct = (last - prev) / prev * 100.0
        items.append({
            "name": name,
            "last": fmt_number(last, dp),
            "pct": fmt_percent(pct) if pct is not None else "--",
            "is_up": (pct or 0) > 0,
            "is_down": (pct or 0) < 0,
        })
    return items
