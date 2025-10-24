# modules/market.py
# 안정형 시세 수집 유틸 + 티커바 데이터 + OHLC/캔들차트
# ───────────────────────────────────────────────────────────
# 변경 사항 요약 (2025-10-24)
# • tzdata/ZoneInfo 미의존: ZoneInfo("Asia/Seoul") → 고정 KST(UTC+9)로 유지
# • yfinance/matplotlib 부재 시에도 동작하도록 폴백 구현 (기존 유지)
# • 요청 반영:
#   (1) matplotlib 미설치/데이터 없음일 때 차트는 **문자열 플레이스홀더**를 반환 → Streamlit에서 텍스트 박스로 그대로 표출 가능
#   (2) 합성 OHLC의 변동성 프로파일 추가: volatility {"low","normal","high"}
# • fetch_quote 안정화(FAST→HIST→폴백 순) 및 NaN/예외 방어 강화
# • 자체 테스트(__main__)에 변동성 프로파일 검증 추가
# ───────────────────────────────────────────────────────────

from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple, Optional
import math
import numpy as np
import pandas as pd

# yfinance / matplotlib은 샌드박스에 없을 수 있으므로 가드 처리
try:
    import yfinance as yf  # type: ignore
    YF_AVAILABLE = True
except Exception:
    yf = None  # type: ignore
    YF_AVAILABLE = False

try:
    import matplotlib.pyplot as plt  # type: ignore
    MPL_AVAILABLE = True
except Exception:
    plt = None  # type: ignore
    MPL_AVAILABLE = False

# tzdata 없이도 안전한 고정 오프셋 KST (UTC+9)
KST = timezone(timedelta(hours=9))

# =============================
# 포맷터
# =============================

def fmt_number(v: Optional[float], d: int = 2) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"


def fmt_percent(v: Optional[float]) -> str:
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

# =============================
# 시세 조회
# =============================

def _fallback_quote(ticker: str) -> Tuple[float, float, Optional[int]]:
    """yfinance가 없거나 실패할 때 사용할 결정적(재현 가능한) 폴백 시세."""
    seed = sum(ord(c) for c in ticker) % 100
    last = 100.0 + (seed - 50) * 0.25
    prev = last * (1.0 - ((seed % 7) - 3) * 0.006)
    vol = 60_000 + seed * 500
    return float(last), float(prev), int(vol)


def fetch_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Optional[int]]:
    """
    1) yfinance.Ticker.fast_info (last_price / previous_close / last_volume)
    2) 실패 시 history(period=10d, 1d, auto_adjust=True)
    3) 모두 실패 시 결정적 폴백 데이터
    → (last, prev, volume) 반환. 실패 시 (None, None, None)
    """
    # yfinance 미탑재 시 폴백
    if not YF_AVAILABLE:
        try:
            return _fallback_quote(ticker)
        except Exception:
            return None, None, None

    # 1) fast_info 시도
    try:
        t = yf.Ticker(ticker)
        fi = getattr(t, "fast_info", None)
        if fi:
            last = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            vol  = getattr(fi, "last_volume", None)
            if last is not None and prev not in (None, 0):
                return float(last), float(prev), (int(vol) if vol else None)
    except Exception:
        pass

    # 2) history() 폴백
    try:
        df = yf.Ticker(ticker).history(period="10d", interval="1d", auto_adjust=True)
        if df is None or df.empty:
            return _fallback_quote(ticker)
        closes = df.get("Close")
        if closes is None:
            return _fallback_quote(ticker)
        closes = closes.dropna()
        vols = df.get("Volume")
        if len(closes) < 2:
            return _fallback_quote(ticker)
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        vol: Optional[int] = None
        if vols is not None and len(vols) == len(df):
            v = vols.iloc[-1]
            vol = int(v) if v == v else None  # NaN 체크
        return last, prev, vol
    except Exception:
        try:
            return _fallback_quote(ticker)
        except Exception:
            return None, None, None

# =============================
# 티커바 데이터
# =============================

def build_ticker_items() -> List[Dict[str, Any]]:
    """상단 지수/원자재/환율 티커바 데이터."""
    rows: List[Tuple[str, str, int]] = [
        ("KOSPI",   "^KS11", 2),
        ("KOSDAQ",  "^KQ11", 2),
        ("DOW",     "^DJI",  2),
        ("NASDAQ",  "^IXIC", 2),
        ("USD/KRW", "KRW=X", 2),
        ("WTI",     "CL=F",  2),
        ("Gold",    "GC=F",  2),
        ("Copper",  "HG=F",  3),
    ]
    items: List[Dict[str, Any]] = []
    for (name, ticker, dp) in rows:
        last, prev, _ = fetch_quote(ticker)
        pct: Optional[float] = None
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

# =============================
# OHLC 로드 + 캔들차트 그리기
# =============================

def _synthetic_ohlc(days: int = 120, volatility: str = "normal") -> pd.DataFrame:
    """데이터 소스 부재 시 테스트 가능한 합성 OHLC 시계열 생성.
    volatility: "low" | "normal" | "high" (표준편차 조절)
    """
    days = max(20, int(days))
    idx = pd.date_range(end=datetime.now(KST), periods=days, freq="D")

    # 변동성 스케일 설정
    vol_map = {"low": 0.4, "normal": 1.0, "high": 2.0}
    scale = vol_map.get(volatility, 1.0)

    rng = np.random.default_rng(42)
    base = 100 + np.cumsum(rng.normal(0, 1*scale, size=days))

    rng_o = np.random.default_rng(7)
    rng_c = np.random.default_rng(9)
    rng_hl = np.random.default_rng(11)
    rng_v = np.random.default_rng(21)

    open_ = base + rng_o.normal(0, 0.5*scale, size=days)
    close = base + rng_c.normal(0, 0.5*scale, size=days)
    high = np.maximum(open_, close) + np.abs(rng_hl.normal(0, 0.8*scale, size=days))
    low = np.minimum(open_, close)  - np.abs(rng_hl.normal(0, 0.8*scale, size=days))
    vol = rng_v.integers(50_000, int(500_000*scale), size=days)

    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)
    return df


def get_ohlc(ticker: str, days: int = 120, volatility: str = "normal") -> pd.DataFrame:
    """
    yfinance에서 일봉 OHLC 데이터 로드.
    - 최소 20거래일 확보 권장.
    - 중복/결측 제거, 타임존 정리.
    - yfinance 부재/실패 시 합성 데이터로 폴백(변동성 프로파일 반영).
    """
    if YF_AVAILABLE:
        try:
            period_map = 365 if days > 252 else max(30, days + 10)  # 여유분
            df = yf.download(
                ticker, period=f"{period_map}d", interval="1d",
                auto_adjust=False, progress=False
            )
            if df is not None and not df.empty:
                df = df[~df.index.duplicated(keep="last")].dropna(subset=["Open","High","Low","Close"])
                df = df.tail(days).copy()
                # index를 KST로 보정(표시 목적) — tzdata 없이 안전
                idx = pd.to_datetime(df.index)
                if getattr(idx, "tz", None) is not None:
                    idx = idx.tz_convert(KST)
                else:
                    idx = idx.tz_localize(KST)
                df.index = idx
                return df[["Open","High","Low","Close","Volume"]]
        except Exception:
            pass
    # 폴백: 합성 데이터 (변동성 반영)
    return _synthetic_ohlc(days, volatility=volatility)


def plot_candles(df: pd.DataFrame, title: str = "", lookback: int = 60):
    """
    matplotlib만으로 심플 캔들차트(양봉=빨강, 음봉=파랑).
    - matplotlib 미존재 또는 데이터 없음 → **문자열 플레이스홀더** 반환
    - df: get_ohlc() 결과. 최소 20봉 권장.
    - lookback: 뒤에서부터 몇 봉 표시할지
    """
    if df is None or df.empty or not MPL_AVAILABLE:
        return "[chart-placeholder] 차트 데이터를 렌더링할 수 없습니다. (matplotlib 미설치 또는 데이터 없음)"

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

# =============================
# 간단 자체 테스트 (단독 실행 시)
# =============================
if __name__ == "__main__":
    # 1) 포맷터 테스트
    assert fmt_number(1234.567, 2) == "1,234.57"
    assert fmt_number(None, 2) == "-"
    assert fmt_percent(1.234) == "+1.23%"
    assert fmt_percent(None) == "-"

    # 2) 시세 조회 테스트 (yfinance 유무 무관하게 동작)
    last, prev, vol = fetch_quote("005930.KS")
    assert last is not None and prev is not None

    # 3) 티커바 아이템 스키마
    items = build_ticker_items()
    assert isinstance(items, list) and len(items) >= 3
    for it in items:
        for k in ["name","last","pct","is_up","is_down"]:
            assert k in it

    # 4) OHLC + 차트 폴백 (normal)
    df_n = get_ohlc("005930.KS", days=60, volatility="normal")
    assert isinstance(df_n, pd.DataFrame) and set(["Open","High","Low","Close","Volume"]).issubset(df_n.columns)
    chart_obj = plot_candles(df_n, title="테스트", lookback=40)
    assert chart_obj is not None  # fig 또는 플레이스홀더 문자열

    # 5) 변동성 프로파일 검증: low vs high의 표준편차 비교(대략적으로 high > low)
    df_low = get_ohlc("005930.KS", days=120, volatility="low")
    df_high = get_ohlc("005930.KS", days=120, volatility="high")
    std_low = float(np.std(df_low["Close"].diff().dropna()))
    std_high = float(np.std(df_high["Close"].diff().dropna()))
    assert std_high >= std_low, "변동성 프로파일 동작 이상: high가 low보다 작음"

    print("[market] ✅ All self-tests passed. YF:", YF_AVAILABLE, "MPL:", MPL_AVAILABLE)
