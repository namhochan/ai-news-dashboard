# -*- coding: utf-8 -*-
# modules/market.py
# 시세 유틸 (yfinance 우선, Yahoo Quote API → Chart API 폴백)
# v3.7.2

from __future__ import annotations
import math
import time
from functools import lru_cache
from typing import Optional, Tuple

import numpy as np

# ----- yfinance (있으면 우선 사용) -----
try:
    import yfinance as yf  # type: ignore
    _YF = True
except Exception:
    yf = None  # type: ignore
    _YF = False

# ----- HTTP -----
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

# ----- Yahoo Quote API (정규장 기준 값) -----
@lru_cache(maxsize=256)
def _fetch_yahoo_quote_once(symbol: str) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    enc = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={enc}"
    try:
        j = _http_json(url)
        res = (j.get("quoteResponse", {}) or {}).get("result", [])
        if not res:
            return None, None, None
        q = res[0]
        last = q.get("regularMarketPrice")
        prev = q.get("regularMarketPreviousClose")
        vol  = q.get("regularMarketVolume")
        if last is None or prev is None:
            return None, None, None
        return float(last), float(prev), (int(vol) if isinstance(vol, (int, float)) else None)
    except Exception:
        return None, None, None

# ----- Yahoo Chart API (최후의 수단) -----
@lru_cache(maxsize=256)
def _fetch_yahoo_chart_once(symbol: str) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    enc = quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{enc}?range=5d&interval=1d&includePrePost=false"
    try:
        j = _http_json(url)
        res = j.get("chart", {}).get("result", [])
        if not res:
            return None, None, None
        r0 = res[0]
        q = (r0.get("indicators", {}) or {}).get("quote", [{}])[0]
        closes = q.get("close") or []
        vols   = q.get("volume") or []
        closes = [c for c in closes if isinstance(c, (int, float))]
        if len(closes) < 2:
            return None, None, None
        last = float(closes[-1])
        prev = float(closes[-2])
        vol  = int(vols[-1]) if vols and isinstance(vols[-1], (int, float)) else None
        return last, prev, vol
    except Exception:
        return None, None, None

# ----- 짧은 TTL 메모리 캐시 -----
_mem_cache: dict = {}
def _memo(fn, symbol: str, ttl: float = 3.0):
    now = time.time()
    k = (fn.__name__, symbol)
    v = _mem_cache.get(k)
    if v and (now - v[0]) < ttl:
        return v[1]
    data = fn(symbol)
    _mem_cache[k] = (now, data)
    return data

# ====== 외부에 노출되는 함수들 ======
def fetch_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """
    (last, prev, volume) 반환
    1) yfinance fast_info/history
    2) Yahoo Quote API (정규장 값) ← 정확도 우선
    3) Yahoo Chart API (최후의 수단)
    """
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

    q = _memo(_fetch_yahoo_quote_once, ticker)
    if q != (None, None, None):
        return q

    return _memo(_fetch_yahoo_chart_once, ticker)

def fmt_number(v, d: int = 2) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{float(v):,.{int(d)}f}"
    except Exception:
        return "-"

def fmt_percent(v) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{float(v):+.2f}%"
    except Exception:
        return "-"

def build_ticker_items():
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

# ---- (선택) OHLC + 캔들차트 ----
import pandas as pd
import matplotlib.pyplot as plt

def get_ohlc(ticker: str, days: int = 120) -> pd.DataFrame:
    if not _YF:
        return pd.DataFrame()
    period_map = 365 if days > 252 else max(30, days + 10)
    try:
        df = yf.download(ticker, period=f"{period_map}d", interval="1d", auto_adjust=False, progress=False)
    except Exception:
        return pd.DataFrame()
    if df is None or df.empty:
        return pd.DataFrame()
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["Open","High","Low","Close"])
    return df[["Open","High","Low","Close","Volume"]].tail(days).copy()

def plot_candles(df: pd.DataFrame, title: str = "", lookback: int = 60):
    if df is None or df.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "차트 데이터 없음", ha="center", va="center")
        ax.axis("off")
        return fig
    data = df.tail(max(20, lookback)).copy()
    x = np.arange(len(data))
    o, h, l, c = data["Open"].values, data["High"].values, data["Low"].values, data["Close"].values
    fig, ax = plt.subplots(figsize=(8, 3))
    width = 0.6
    for i in range(len(data)):
        color = "#d93025" if c[i] >= o[i] else "#1a73e8"
        ax.vlines(x=i, ymin=l[i], ymax=h[i], colors=color, linewidth=1)
        top, bottom = max(o[i], c[i]), min(o[i], c[i])
        height = max(top - bottom, 1e-6)
        ax.add_patch(plt.Rectangle((i - width/2, bottom), width, height, color=color, alpha=0.8, linewidth=0))
    ax.set_xlim(-1, len(data))
    ax.set_title(title or "일봉 차트", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.25)
    step = max(1, len(data)//6)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([data.index[i].strftime("%m-%d") for i in x[::step]])
    ax.tick_params(axis='x', labelsize=9); ax.tick_params(axis='y', labelsize=9)
    fig.tight_layout()
    return fig
