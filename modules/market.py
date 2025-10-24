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
    조정 종가(Adj Close, auto_adjust=True) 기준으로
    '마지막 종가'와 '직전 종가'를 안전하게 반환 + 마지막 거래량.
    """
    try:
        df = yf.download(
            ticker, period="14d", interval="1d",
            auto_adjust=True, progress=False
        )
        if df is None or df.empty:
            return None, None, None

        closes = df["Close"].dropna()
        vols   = df.get("Volume", None)

        if len(closes) < 2:
            return None, None, None

        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        vol  = int(vols.iloc[-1]) if vols is not None and not np.isnan(vols.iloc[-1]) else None
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
        if last and prev:
            pct = (last - prev) / prev * 100.0
        items.append({
            "name": name,
            "last": fmt_number(last, dp),
            "pct": fmt_percent(pct) if pct is not None else "--",
            "is_up": (pct or 0) > 0,
            "is_down": (pct or 0) < 0,
        })
    return items
