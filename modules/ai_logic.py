# modules/ai_logic.py
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from .market import fetch_quote, fmt_percent, fmt_number
from .news import THEME_STOCKS

def summarize_news_titles(news_list, topn=5):
    """아주 간단 요약: 제목에서 상위 n개 문장"""
    titles = [n.get("title","") for n in news_list if n.get("title")]
    if not titles: return []
    joined = " ".join(titles)
    sents = [s.strip() for s in joined.split(".") if len(s.strip())>15]
    return sents[:topn]

def calc_theme_strength(news_count, avg_delta):
    """테마강도(1~5): 뉴스빈도(60%) + 평균등락(40%)"""
    freq_score  = min(news_count/20, 1.0)
    price_score = min(max((avg_delta + 5)/10, 0), 1.0)
    total = (freq_score*0.6 + price_score*0.4) * 5
    return round(total, 1)

def calc_risk_level(avg_delta):
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

def pick_promising_stocks(theme_rows, top_n=5):
    """
    테마 강도 + 개별 등락률을 통한 점수로 상위 종목 선별
    theme_rows: [{'테마':..., '뉴스건수':...}, ...]
    """
    cands=[]
    for tr in theme_rows[:8]:
        theme = tr["테마"]
        news_count = tr["뉴스건수"]
        for name, ticker in THEME_STOCKS.get(theme, []):
            try:
                last, prev = fetch_quote(ticker)
                if not last or not prev: 
                    continue
                delta = (last - prev) / prev * 100
                score = news_count*0.3 + delta*0.7
                cands.append({
                    "테마": theme, "종목명": name, "티커": ticker,
                    "등락률(%)": round(delta,2), "뉴스빈도": news_count,
                    "AI점수": round(score,2)
                })
            except Exception:
                continue
    df = pd.DataFrame(cands)
    if df.empty: return df
    return df.sort_values("AI점수", ascending=False).head(top_n)

def theme_price_snapshot(theme):
    """테마 내 종목들의 현재가/변동률 스냅샷"""
    rows=[]
    for name, ticker in THEME_STOCKS.get(theme, []):
        try:
            last, prev = fetch_quote(ticker)
            if last and prev:
                delta = (last - prev)/prev*100
                rows.append({"종목":name,"티커":ticker,"현재가":fmt_number(last,0),"등락률":fmt_percent(delta)})
        except Exception:
            pass
    return rows
