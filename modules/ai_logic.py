# -*- coding: utf-8 -*-
import math
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.linear_model import LogisticRegression

def _fmt_percent(v):
    try:
        if v is None or math.isnan(v): return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

def fetch_quote_safe(ticker: str):
    """yfinance 안정 수집: fast_info → 7d 종가"""
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass
    try:
        df = yf.download(ticker, period="7d", interval="1d",
                         progress=False, auto_adjust=False)
        c = df.get("Close")
        if c is None or c.dropna().empty:
            return None, None
        c = c.dropna()
        last = float(c.iloc[-1])
        prev = float(c.iloc[-2]) if len(c) >= 2 else None
        return last, prev
    except Exception:
        return None, None

# ===== 상승확률(간단 로지스틱) =====
def _rsi(series: pd.Series, period: int = 14):
    d = series.diff()
    up = np.where(d > 0, d, 0.0)
    dn = np.where(d < 0, -d, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_dn = pd.Series(dn, index=series.index).rolling(period).mean().replace(0, np.nan)
    rs = roll_up / roll_dn
    return (100 - (100 / (1 + rs))).fillna(50)

def _macd(series: pd.Series, fast=12, slow=26, sig=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    line = ema_f - ema_s
    signal = line.ewm(span=sig, adjust=False).mean()
    hist = line - signal
    return line, signal, hist

def _load_hist(ticker: str, period="2y"):
    df = yf.download(ticker, period=period, interval="1d",
                     auto_adjust=True, progress=False)
    df = df[~df.index.duplicated(keep="last")].dropna()
    return df

def _build_features(df: pd.DataFrame):
    px = df["Close"]
    f = pd.DataFrame(index=df.index)
    f["ret_1d"] = px.pct_change(1)
    f["ret_5d"] = px.pct_change(5)
    f["ret_10d"] = px.pct_change(10)
    f["vol_5d"] = px.pct_change().rolling(5).std()
    f["vol_20d"] = px.pct_change().rolling(20).std()
    f["rsi_14"] = _rsi(px, 14)
    macd, sig, hist = _macd(px)
    f["macd"] = macd; f["macd_sig"] = sig; f["macd_hist"] = hist
    ma5 = px.rolling(5).mean(); ma20 = px.rolling(20).mean()
    f["ma5_gap"] = (px - ma5) / ma5
    f["ma20_gap"] = (px - ma20) / ma20
    y = (px.shift(-1) > px).astype(int)
    return pd.concat([f, y.rename("y")], axis=1).dropna()

def predict_tomorrow_prob(ticker: str):
    """다음날 상승확률 / 최근 3개 평균확률"""
    hist = _load_hist(ticker)
    if hist.empty: return None, None
    feat = _build_features(hist)
    if len(feat) < 120: return None, None
    data = feat.tail(300)
    X = data.drop(columns=["y"]).values
    y = data["y"].values
    n = len(data); split = max(60, n - 3)
    X_train, y_train = X[:split], y[:split]
    X_pred = X[split:]
    m = LogisticRegression(max_iter=200)
    m.fit(X_train, y_train)
    prob = m.predict_proba(X_pred)[:, 1]
    p1 = float(prob[0]) if len(prob) else None
    p3 = float(prob.mean()) if len(prob) else None
    return p1, p3
