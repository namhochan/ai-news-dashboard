# modules/ai_logic.py
# 간단 요약/키워드, 테마 리포트, 유망종목(테마다 1종목) 선택 로직

from __future__ import annotations
import re
import numpy as np
import pandas as pd
from collections import Counter
from modules.market import fetch_quote

# ---------- 요약/키워드 ----------
def extract_keywords(titles, topn=10):
    words = []
    for t in titles:
        t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t or "")
        words.extend([w for w in t.split() if len(w) >= 2])
    return [w for w, _ in Counter(words).most_common(topn)]

def summarize_sentences(texts, n_sent=5):
    if not texts:
        return []
    full = " ".join(texts)
    sents = re.split(r'[.!?]\s+', full)
    sents = [s.strip() for s in sents if len(s.strip()) > 20]
    scores = {s: sum(w in full for w in s.split()) for s in sents}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [s for s, _ in ranked[:n_sent]]

# ---------- 테마 강도/리스크 ----------
def calc_theme_strength(count, avg_delta):
    freq = min(count / 20.0, 1.0)
    price = min(max((avg_delta + 5) / 10, 0), 1.0)
    return round((freq * 0.6 + price * 0.4) * 5, 1)

def calc_risk_level(avg_delta):
    if avg_delta >= 3: return 1
    if avg_delta >= 1: return 2
    if avg_delta >= -1: return 3
    if avg_delta >= -3: return 4
    return 5

def make_theme_report(theme_rows, theme_stocks_map):
    rows = []
    for tr in theme_rows[:8]:
        theme = tr["theme"]
        stocks = theme_stocks_map.get(theme, [])
        deltas = []
        for _, t in stocks:
            last, prev, _ = fetch_quote(t)
            if last and prev:
                deltas.append((last - prev) / prev * 100.0)
        avg_delta = float(np.mean(deltas)) if deltas else 0.0
        rows.append({
            "테마": theme,
            "뉴스건수": tr["count"],
            "평균등락(%)": round(avg_delta, 2),
            "테마강도(1~5)": calc_theme_strength(tr["count"], avg_delta),
            "리스크(1~5)": calc_risk_level(avg_delta),
        })
    return pd.DataFrame(rows)

# ---------- 유망 종목 (테마다 1종목) ----------
MAX_ABS_MOVE = 25.0     # 점수 계산용 캡(±25%)
OUTLIER_DROP = 30.0     # 절대 30% 넘으면 제외
MIN_VOLUME   = 100_000  # 거래량 하한

def _safe_delta_pct(ticker: str):
    last, prev, vol = fetch_quote(ticker)
    if not last or not prev:
        return None
    pct = (last - prev) / prev * 100.0
    if vol is not None and vol < MIN_VOLUME:
        return None
    if abs(pct) > OUTLIER_DROP:
        return None
    pct_for_score = float(np.clip(pct, -MAX_ABS_MOVE, MAX_ABS_MOVE))
    return pct, pct_for_score, vol

def pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=5):
    """
    테마다 1종목씩 뽑아 Top N 구성.
    스코어 = 뉴스빈도(정규화) * 0.4 + (캡핑된 일간등락률/MAX_ABS_MOVE) * 0.6
    """
    selected = []
    for tr in theme_rows:
        theme = tr["theme"]
        freq  = tr["count"]
        best  = None
        for name, ticker in theme_stocks_map.get(theme, []):
            res = _safe_delta_pct(ticker)
            if res is None:
                continue
            real_pct, score_pct, vol = res
            freq_score = min(freq / 20.0, 1.0)
            score = freq_score * 0.4 + (score_pct / MAX_ABS_MOVE) * 0.6  # -1~1
            cand = {
                "테마": theme, "종목명": name, "티커": ticker,
                "등락률(%)": round(real_pct, 2),
                "뉴스빈도": freq,
                "AI점수": round(score * 100, 2),
                "거래량": vol
            }
            if best is None or cand["AI점수"] > best["AI점수"]:
                best = cand
        if best:
            selected.append(best)
        if len(selected) >= top_n:
            break
    selected.sort(key=lambda x: x["AI점수"], reverse=True)
    return pd.DataFrame(selected)
