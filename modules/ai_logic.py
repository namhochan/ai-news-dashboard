# -*- coding: utf-8 -*-
# modules/ai_logic.py – 요약/테마 리포트/유망종목 + 저장 유틸 (v3.7.1+R)

from __future__ import annotations
from typing import List, Dict, Any, Iterable, Optional, Tuple
import re, os, json
from collections import Counter
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

# 시세 유틸 (market 모듈이 yfinance 유무/네트워크 방어)
try:
    from modules.market import fetch_quote
except Exception:
    def fetch_quote(_ticker: str): return (None, None, None)

KST = timezone(timedelta(hours=9))

# ---------- 키워드/요약 ----------
def extract_keywords(titles: Iterable[str], topn: int = 10) -> List[str]:
    words: List[str] = []
    for t in titles or []:
        t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t or "")
        words.extend([w for w in t.split() if len(w) >= 2])
    return [w for w, _ in Counter(words).most_common(max(1, int(topn)))]

def summarize_sentences(texts: Iterable[str], n_sent: int = 5) -> List[str]:
    texts = list(texts or [])
    if not texts: return []
    full = " ".join(texts)
    sents = re.split(r"[.!?]\s+", full)
    sents = [s.strip() for s in sents if len(s.strip()) > 20]
    if not sents: return []
    scores = {s: sum((w in full) for w in s.split()) for s in sents}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [s for s, _ in ranked[:max(1, int(n_sent))]]

# ---------- 테마 지표 ----------
def calc_theme_strength(count: int, avg_delta: float) -> float:
    freq = min(max(float(count) / 20.0, 0.0), 1.0)
    price = min(max((float(avg_delta) + 5.0) / 10.0, 0.0), 1.0)
    return round((freq * 0.6 + price * 0.4) * 5.0, 1)

def calc_risk_level(avg_delta: float) -> int:
    a = float(avg_delta)
    if a >= 3: return 1
    if a >= 1: return 2
    if a >= -1: return 3
    if a >= -3: return 4
    return 5

# ---------- 테마 리포트 ----------
def make_theme_report(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for tr in (theme_rows or [])[:8]:
        theme = tr.get("theme")
        if not theme: continue
        deltas: List[float] = []
        for _, t in theme_stocks_map.get(theme, []):
            last, prev, _ = fetch_quote(t)
            if last and prev:
                try: deltas.append((float(last) - float(prev)) / float(prev) * 100.0)
                except Exception: pass
        avg_delta = float(np.mean(deltas)) if deltas else 0.0
        rows.append({
            "테마": theme,
            "뉴스건수": int(tr.get("count", 0)),
            "평균등락(%)": round(avg_delta, 2),
            "테마강도(1~5)": calc_theme_strength(int(tr.get("count", 0)), avg_delta),
            "리스크(1~5)": calc_risk_level(avg_delta),
        })
    return pd.DataFrame(rows)

# ---------- 유망 종목 ----------
MAX_ABS_MOVE = 25.0
OUTLIER_DROP = 35.0
MIN_VOLUME   = 30_000

def _safe_delta_pct(ticker: str):
    last, prev, vol = fetch_quote(ticker)
    if not last or not prev: return None
    try: pct = (float(last) - float(prev)) / float(prev) * 100.0
    except Exception: return None
    if vol is not None and vol < MIN_VOLUME: return None
    if abs(pct) > OUTLIER_DROP: return None
    pct_for_score = float(np.clip(pct, -MAX_ABS_MOVE, MAX_ABS_MOVE))
    return pct, pct_for_score, vol

def pick_promising_by_theme_once(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]], top_n: int = 5) -> pd.DataFrame:
    selected: List[Dict[str, Any]] = []
    for tr in theme_rows or []:
        theme = tr.get("theme")
        if not theme: continue
        freq = int(tr.get("count", 0))
        best = None
        for name, ticker in theme_stocks_map.get(theme, []):
            res = _safe_delta_pct(ticker)
            if res is None: continue
            real_pct, score_pct, vol = res
            score = min(freq / 20.0, 1.0) * 0.4 + (score_pct / MAX_ABS_MOVE) * 0.6
            cand = {
                "테마": theme, "종목명": name, "티커": ticker,
                "등락률(%)": round(float(real_pct), 2),
                "뉴스빈도": freq,
                "AI점수": round(score * 100.0, 2),
                "거래량": vol,
            }
            if best is None or cand["AI점수"] > best["AI점수"]:
                best = cand
        if best: selected.append(best)
        if len(selected) >= int(top_n): break
    selected.sort(key=lambda x: x["AI점수"], reverse=True)
    return pd.DataFrame(selected)

# ---------- 저장 유틸 ----------
def save_report_and_picks(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]], out_dir: str = "reports", top_n: int = 5, prefix: str = "export") -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    report_csv  = os.path.join(out_dir, f"{prefix}_theme_report_{ts}.csv")
    report_json = os.path.join(out_dir, f"{prefix}_theme_report_{ts}.json")
    pd.DataFrame(theme_rows).to_csv(report_csv, index=False, encoding="utf-8")
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(theme_rows, f, ensure_ascii=False, indent=2)
    picks_df = pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=top_n)
    picks_csv  = os.path.join(out_dir, f"{prefix}_promising_picks_{ts}.csv")
    picks_json = os.path.join(out_dir, f"{prefix}_promising_picks_{ts}.json")
    if not picks_df.empty:
        picks_df.to_csv(picks_csv, index=False, encoding="utf-8")
        with open(picks_json, "w", encoding="utf-8") as f:
            json.dump(picks_df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    else:
        open(picks_csv, "a", encoding="utf-8").close()
        open(picks_json, "a", encoding="utf-8").close()
    return {"report_csv": report_csv, "report_json": report_json, "picks_csv": picks_csv, "picks_json": picks_json}
