# -*- coding: utf-8 -*-
# modules/analyzer.py
# 간단 종목 분석 & 기록 (yfinance 없으면 요약만 반환)
# v3.7.1+R

from __future__ import annotations
import os, json, sqlite3
from datetime import datetime, timezone, timedelta
from typing import Tuple, Dict, Any, List

import pandas as pd

# yfinance 안전 임포트
try:
    import yfinance as yf  # type: ignore
    _YF = True
except Exception:
    yf = None  # type: ignore
    _YF = False

KST = timezone(timedelta(hours=9))
DB_DIR = "data"
DB_PATH = os.path.join(DB_DIR, "analysis.db")

def init_db() -> None:
    os.makedirs(DB_DIR, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          ts TEXT NOT NULL,
          name TEXT,
          ticker TEXT,
          summary TEXT,
          payload TEXT
        )
        """)
        conn.commit()

def _fetch_basic(ticker: str) -> Dict[str, Any]:
    if not _YF:
        return {}
    try:
        t = yf.Ticker(ticker)
        info = {}
        fi = getattr(t, "fast_info", None)
        if fi:
            info["last"] = getattr(fi, "last_price", None)
            info["prev"] = getattr(fi, "previous_close", None)
            info["volume"] = getattr(fi, "last_volume", None)
        # 보수적으로 최근 30일 종가
        hist = t.history(period="30d", interval="1d", auto_adjust=True)
        if hist is not None and not hist.empty:
            info["close_series"] = hist["Close"].dropna().tolist()
        return info
    except Exception:
        return {}

def analyze_stock(name: str, ticker: str) -> Tuple[str, Dict[str, Any]]:
    """
    간단 분석:
    - fast_info/30일 종가 수집
    - 전일 대비 %, 7일/30일 추세 요약
    """
    payload = _fetch_basic(ticker)
    last, prev = payload.get("last"), payload.get("prev")
    change_pct = None
    if isinstance(last, (int, float)) and isinstance(prev, (int, float)) and prev:
        change_pct = (last - prev) / prev * 100.0

    series = payload.get("close_series") or []
    trend7, trend30 = None, None
    if len(series) >= 7:
        trend7 = (series[-1] - series[-7]) / series[-7] * 100.0
    if len(series) >= 30:
        trend30 = (series[-1] - series[0]) / series[0] * 100.0

    summary = f"{name}({ticker})"
    parts = []
    if change_pct is not None:
        parts.append(f"전일대비 {change_pct:+.2f}%")
    if trend7 is not None:
        parts.append(f"7일 {trend7:+.2f}%")
    if trend30 is not None:
        parts.append(f"30일 {trend30:+.2f}%")
    if not parts:
        parts.append("데이터 제한으로 간단 요약만 제공합니다.")
    summary += " · " + ", ".join(parts)

    # DB 저장
    rec = {
        "name": name, "ticker": ticker,
        "last": last, "prev": prev,
        "change_pct": change_pct,
        "trend7": trend7, "trend30": trend30,
    }
    ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO analyses(ts, name, ticker, summary, payload) VALUES (?, ?, ?, ?, ?)",
            (ts, name, ticker, summary, json.dumps(rec, ensure_ascii=False))
        )
        conn.commit()

    return summary, rec

def load_recent(limit: int = 10) -> pd.DataFrame:
    if not os.path.exists(DB_PATH):
        return pd.DataFrame(columns=["시간", "종목명", "티커", "요약"])
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "SELECT ts, name, ticker, summary FROM analyses ORDER BY id DESC LIMIT ?",
            (int(limit),)
        )
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["시간", "종목명", "티커", "요약"])
    return df
