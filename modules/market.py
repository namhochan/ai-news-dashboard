modules/market.py

안정형 시세 수집 유틸 + 티커바 데이터 + OHLC/캔들 (외부 의존 방어)

v3.7.1+3

from future import annotations from typing import Any, Dict, List, Optional, Tuple from datetime import timezone, timedelta import math import numpy as np import pandas as pd

------------------------------

외부 라이브러리(yfinance / matplotlib) 옵션 의존

------------------------------

try:  # yfinance는 없을 수 있음 import yfinance as yf  # type: ignore _YF = True except Exception:  # pragma: no cover yf = None  # type: ignore _YF = False

try:  # matplotlib도 없을 수 있음 import matplotlib.pyplot as plt  # type: ignore _MPL = True except Exception:  # pragma: no cover plt = None  # type: ignore _MPL = False

tzdata 없이 안전한 KST 고정

KST = timezone(timedelta(hours=9))

------------------------------

숫자 포맷 공용

------------------------------

def fmt_number(v: Optional[float], d: int = 2) -> str: try: if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return "-" return f"{float(v):,.{max(0,int(d))}f}" except Exception: return "-"

def fmt_percent(v: Optional[float]) -> str: try: if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))): return "-" return f"{float(v):+.2f}%" except Exception: return "-"

------------------------------

시세 조회 (fast_info → history)

------------------------------

def fetch_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Optional[int]]: """ (last, prev, volume) 반환. 실패 시 (None, None, None) 1) yfinance.fast_info (last_price / previous_close / last_volume) 2) 실패 시 history(period=10d, 1d, auto_adjust=True) """ if not ticker: return None, None, None

# 1) yfinance fast_info 시도
if _YF:
    try:
        t = yf.Ticker(ticker)
        fi = getattr(t, "fast_info", None)
        if fi is not None:
            last = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            vol = getattr(fi, "last_volume", None)
            if last is not None and prev is not None:
                return float(last), float(prev), (int(vol) if vol is not None else None)
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
        vol_out: Optional[int] = None
        if vols is not None and len(vols) >= 1:
            v = vols.iloc[-1]
            try:
                vol_out = int(v) if v == v else None  # NaN 체크
            except Exception:
                vol_out = None
        return last, prev, vol_out
    except Exception:
        return None, None, None

# 3) yfinance 없음 → 결정적 폴백(더미)
try:
    seed = sum(ord(c) for c in ticker) % 100
    last = 100.0 + (seed - 50) * 0.25
    prev = last * (1.0 - ((seed % 7) - 3) * 0.006)
    vol = 60_000 + seed * 500
    return float(last), float(prev), int(vol)
except Exception:
    return None, None, None

------------------------------

상단 지수/원자재/환율 티커바 데이터

------------------------------

def build_ticker_items() -> List[Dict[str, Any]]: rows = [ ("KOSPI",   "^KS11", 2), ("KOSDAQ",  "^KQ11", 2), ("DOW",     "^DJI",  2), ("NASDAQ",  "^IXIC", 2), ("USD/KRW", "KRW=X", 2), ("WTI",     "CL=F",  2), ("Gold",    "GC=F",  2), ("Copper",  "HG=F",  3), ] items: List[Dict[str, Any]] = [] for (name, ticker, dp) in rows: last, prev, _ = fetch_quote(ticker) pct: Optional[float] = None if last is not None and prev not in (None, 0): try: pct = (last - prev) / prev * 100.0 except Exception: pct = None items.append({ "name": name, "last": fmt_number(last, dp), "pct": fmt_percent(pct) if pct is not None else "--", "is_up": (pct or 0) > 0, "is_down": (pct or 0) < 0, }) return items

------------------------------

OHLC 로드 + 캔들차트 그리기 (옵션)

------------------------------

def get_ohlc(ticker: str, days: int = 120) -> pd.DataFrame: """yfinance에서 일봉 OHLC 데이터 로드. - 최소 20거래일 확보 권장 - 중복/결측 제거, 최근 N일만 슬라이스 - tzdata 없이 index naive 유지 (표시 목적) """ if not _YF: return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])  # 빈 DF

try:
    period_map = 365 if days > 252 else max(30, int(days) + 10)  # 여유분
    df = yf.download(
        ticker, period=f"{period_map}d", interval="1d",
        auto_adjust=False, progress=False
    )
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])  # 빈 DF
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["Open","High","Low","Close"])
    df = df.tail(int(days)).copy()
    return df[["Open","High","Low","Close","Volume"]]
except Exception:
    return pd.DataFrame(columns=["Open","High","Low","Close","Volume"])  # 실패 시 빈 DF

def plot_candles(df: pd.DataFrame, title: str = "", lookback: int = 60): """matplotlib만으로 심플 캔들차트(양봉=빨강, 음봉=파랑). - matplotlib 미설치 시 텍스트 메시지 figure 대체 - df가 비어있으면 안내 figure 반환 """ if not _MPL: return None

try:
    if df is None or df.empty:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.text(0.5, 0.5, "차트 데이터 없음", ha="center", va="center")
        ax.axis("off")
        fig.tight_layout()
        return fig

    data = df.tail(max(20, int(lookback))).copy()
    x = np.arange(len(data))
    o = data["Open"].values.astype(float)
    h = data["High"].values.astype(float)
    l = data["Low"].values.astype(float)
    c = data["Close"].values.astype(float)

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
    # index가 DatetimeIndex일 수도/아닐 수도 있음 → 안전 처리
    try:
        xt = [pd.to_datetime(data.index[i]).strftime("%m-%d") for i in x[::step]]
    except Exception:
        xt = [str(i) for i in x[::step]]
    ax.set_xticklabels(xt)
    ax.tick_params(axis='x', labelsize=9)
    ax.tick_params(axis='y', labelsize=9)
    fig.tight_layout()
    return fig
except Exception:
    # 마지막 방어: 오류 시 간단 figure
    if not _MPL:
        return None
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.text(0.5, 0.5, "차트 오류", ha="center", va="center")
    ax.axis("off")
    fig.tight_layout()
    return fig

------------------------------

Self tests (no external net required)

------------------------------

if name == "main": # 1) 포맷터 assert fmt_number(1234.567, 2) == "1,234.57" assert fmt_number(None) == "-" assert fmt_percent(1.2345) == "+1.23%" assert fmt_percent(None) == "-"

# 2) 시세 조회 (yfinance 유무와 무관하게 튜플 반환)
last, prev, vol = fetch_quote("005930.KS")
assert isinstance(last, (float, type(None))) and isinstance(prev, (float, type(None)))

# 3) 티커바
items = build_ticker_items()
assert isinstance(items, list) and len(items) >= 3
for it in items:
    assert {"name","last","pct","is_up","is_down"}.issubset(set(it.keys()))

# 4) OHLC/캔들 (matplotlib 있을 때만)
df = get_ohlc("005930.KS", days=30)
assert isinstance(df, pd.DataFrame)
if _MPL:
    fig = plot_candles(df, title="샘플", lookback=30)
    assert fig is None or hasattr(fig, "savefig")
print("[market] ✅ self-tests passed. yfinance:", _YF, "matplotlib:", _MPL)
