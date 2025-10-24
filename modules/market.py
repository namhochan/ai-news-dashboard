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
    # --- OHLC 로드 + 캔들차트 그리기 ---------------------------------
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

def get_ohlc(ticker: str, days: int = 120) -> pd.DataFrame:
    """
    yfinance에서 일봉 OHLC 데이터 로드.
    - 최소 20거래일 확보를 권장.
    - 중복/결측 제거, 타임존 정리.
    """
    period_map = 365 if days > 252 else max(30, days + 10)  # 여유분
    df = yf.download(
        ticker, period=f"{period_map}d", interval="1d",
        auto_adjust=False, progress=False
    )
    if df is None or df.empty:
        return pd.DataFrame()

    df = df[~df.index.duplicated(keep="last")].dropna(subset=["Open","High","Low","Close"])
    # 최근 N일만 슬라이스
    df = df.tail(days).copy()
    # index를 KST로 보정(표시 목적)
    df.index = pd.to_datetime(df.index).tz_localize(None).tz_localize(KST, nonexistent="shift_forward", ambiguous="NaT")
    return df[["Open","High","Low","Close","Volume"]]

def plot_candles(df: pd.DataFrame, title: str = "", lookback: int = 60):
    """
    matplotlib만으로 심플 캔들차트(양봉=빨강, 음봉=파랑).
    df: get_ohlc() 결과. 최소 20봉 권장.
    lookback: 뒤에서부터 몇 봉 표시할지
    """
    if df is None or df.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "차트 데이터 없음", ha="center", va="center")
        ax.axis("off")
        return fig

    data = df.tail(max(20, lookback)).copy()
    x = np.arange(len(data))
    o, h, l, c = data["Open"].values, data["High"].values, data["Low"].values, data["Close"].values

    fig, ax = plt.subplots(figsize=(8, 3))
    width = 0.6  # 몸통 폭

    for i in range(len(data)):
        color = "#d93025" if c[i] >= o[i] else "#1a73e8"  # 양봉=빨강, 음봉=파랑
        # 심지
        ax.vlines(x=i, ymin=l[i], ymax=h[i], colors=color, linewidth=1)
        # 몸통
        top = max(o[i], c[i]); bottom = min(o[i], c[i])
        height = max(top - bottom, 1e-6)
        ax.add_patch(plt.Rectangle((i - width/2, bottom), width, height, color=color, alpha=0.8, linewidth=0))

    ax.set_xlim(-1, len(data))
    ax.set_title(title or "일봉 차트", fontsize=11)
    ax.grid(True, linestyle="--", alpha=0.25)
    # x축 눈금 간략화
    step = max(1, len(data) // 6)
    ax.set_xticks(x[::step])
    ax.set_xticklabels([data.index[i].strftime("%m-%d") for i in x[::step]])
    ax.tick_params(axis='x', labelsize=9)
    ax.tick_params(axis='y', labelsize=9)
    fig.tight_layout()
    return fig
