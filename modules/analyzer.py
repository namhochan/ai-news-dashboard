# -*- coding: utf-8 -*-
# modules/analyzer.py
# 간단 분석 + DB 저장 (옵션 1)

import os, sqlite3, json, datetime as dt
import pandas as pd

from modules.market import fetch_quote           # (last, prev) 반환 가정
from modules.news import fetch_google_news_by_keyword

DB_PATH = "data/analysis.db"
os.makedirs("data", exist_ok=True)

# -------------------------
# DB
# -------------------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker    TEXT,
            name      TEXT,
            date      TEXT,
            summary   TEXT,
            data_json TEXT
        )
    """)
    conn.close()

def save_result(name: str, ticker: str, when: str, summary: str, data: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO analyses (ticker, name, date, summary, data_json) VALUES (?,?,?,?,?)",
        (ticker, name, when, summary, json.dumps(data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()

def load_recent(limit: int = 10) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(
        "SELECT id, date, name, ticker, summary FROM analyses ORDER BY id DESC LIMIT ?",
        conn, params=(limit,)
    )
    conn.close()
    return df

# -------------------------
# 간단 분석
# -------------------------
def _pct(last, prev):
    if not last or not prev or prev == 0:
        return 0.0
    return (last - prev) / prev * 100.0

def analyze_stock(name: str, ticker: str):
    """
    옵션1: 최소 가동 세트
     - 가격 등락
     - 뉴스 3일간 타이틀 요약
     - 간단 리스크/세력/심리 지표(룰베이스)
     - DB 저장
    """
    when = dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 1) 가격
    last, prev = fetch_quote(ticker)
    rate = round(_pct(last, prev), 2)

    # 2) 뉴스 (3일/최대 5개)
    news = []
    try:
        news = fetch_google_news_by_keyword(name, days=3, max_items=5)
    except Exception:
        pass
    news_titles = [n.get("title", "") for n in news if n.get("title")]
    news_summary = " / ".join(news_titles[:3]) if news_titles else "최근 3일 뉴스 없음"

    # 3) 간단 점수 (룰베이스)
    risk_lvl   = 2 if rate >= 1 else (3 if rate >= -1 else 4)
    power_lvl  = 3 if rate >= 0 else 2
    candle_lvl = 3 if rate >= 0 else 2

    data = {
        "메타": {"분석시점": when},
        "기본": {"종목": name, "티커": ticker},
        "가격": {"현재등락률(%)": rate, "현재가": last, "전일종가": prev},
        "요약": {
            "뉴스요약(최근3일)": news_summary,
            "리스크레벨(1낮음-5높음)": risk_lvl,
            "세력강도(1~5)": power_lvl,
            "캔들심리(1~5)": candle_lvl,
        },
        "뉴스제목": news_titles,
    }

    summary = f"[{name}] {rate:+.2f}% · 리스크 {risk_lvl} · 세력 {power_lvl} · 심리 {candle_lvl}"
    save_result(name, ticker, when, summary, data)
    return summary, data
