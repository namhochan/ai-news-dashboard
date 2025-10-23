# -*- coding: utf-8 -*-
"""
AI 요약 · 자동 매핑 · 유망 종목 추천 · (옵션) 3일 예측
- summarize_news(news_list)
- show_ai_recommendations(theme_rows)
- predict_3day(tickers)  # 선택 사용
"""

import re
import difflib
from datetime import datetime
from collections import Counter
from typing import List, Dict, Tuple

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from sklearn.linear_model import LogisticRegression
import FinanceDataReader as fdr

# 내부 모듈
from modules.news import fetch_category_news, THEME_KEYWORDS
from modules.market import fetch_quote

# -----------------------------
# 0) 공용 유틸
# -----------------------------
def _fmt_number(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))): return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def _fmt_percent(v):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))): return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

def _valid_prices(last, prev):
    return last is not None and prev not in (None, 0) and np.isfinite(last) and np.isfinite(prev)

# -----------------------------
# 1) 뉴스 요약/키워드
# -----------------------------
def summarize_news(news_list: List[dict], topn_kw: int = 10, n_sent: int = 5):
    """뉴스 제목/요약으로 키워드 TopN + 간단 요약문(더보기형) 출력"""
    titles = [(n.get("title") or "") for n in news_list]
    bodies = [f"{n.get('title','')} {n.get('desc','')}" for n in news_list]

    # 키워드
    words = []
    for t in titles:
        t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t)
        words += [w for w in t.split() if len(w) >= 2]
    top_kw = [w for w, _ in Counter(words).most_common(topn_kw)]

    st.markdown("### 📌 핵심 키워드")
    st.write(", ".join(top_kw) if top_kw else "-")

    # 요약
    full_text = " ".join(bodies)
    sents = [s.strip() for s in re.split(r"[.!?]\s+", full_text) if len(s.strip()) > 20]
    sents = sents[:n_sent]

    st.markdown("### 📰 핵심 요약문")
    if sents:
        st.markdown(f"**요약:** {sents[0][:140]}...")
        with st.expander("전체 요약문 보기 👇"):
            for s in sents:
                st.markdown(f"- {s}")
    else:
        st.info("요약 데이터를 생성하기에 텍스트가 부족합니다.")

# -----------------------------
# 2) 자동 매핑 (뉴스 ↔ KRX 상장사)
# -----------------------------
@st.cache_data(ttl=3600)
def _load_krx_listings():
    df = fdr.StockListing("KRX")
    df = df.rename(columns={"Symbol":"Code","Name":"Name"})
    for col in ["Name","Sector","Industry"]:
        if col not in df.columns: df[col] = ""
    df["name_l"]     = df["Name"].astype(str).str.lower()
    df["sector_l"]   = df["Sector"].astype(str).str.lower()
    df["industry_l"] = df["Industry"].astype(str).str.lower()
    return df[["Code","Name","Market","Sector","Industry","name_l","sector_l","industry_l"]]

def _kr_ticker(code: str) -> str | None:
    if not code or not re.fullmatch(r"\d{6}", str(code)): return None
    # 간단 추정: 0/1/5/6/9 시작 = .KS, 그 외 .KQ
    return f"{code}.KS" if str(code)[0] in "01569" else f"{code}.KQ"

def _extract_company_mentions(news_all: List[dict], listings: pd.DataFrame,
                              min_len: int = 2, sim_cutoff: float = 0.9) -> Dict[str, dict]:
    """
    뉴스 텍스트에서 상장사 '회사명' 등장/유사어로 언급수 집계
    반환: {회사명: {code, ticker, hits, sector, industry}}
    """
    names = listings["name_l"].tolist()
    idx_by_name = {n: i for i, n in enumerate(names)}
    counts = {}

    for n in news_all:
        text = (f"{n.get('title','')} {n.get('desc','')}".lower()).strip()
        if not text: continue

        # ① 부분일치
        for i, row in listings.iterrows():
            nm = row["name_l"]
            if len(nm) < min_len: continue
            if nm and nm in text:
                code = row["Code"]; key = row["Name"]
                counts.setdefault(key, {"code":code, "ticker":_kr_ticker(code), "hits":0,
                                        "sector":row["Sector"], "industry":row["Industry"]})
                counts[key]["hits"] += 1

        # ② 유사도 보정
        tokens = [t for t in re.split(r"[^가-힣A-Za-z0-9]+", text) if len(t) >= min_len]
        for tok in set(tokens):
            for cand in difflib.get_close_matches(tok, names, n=3, cutoff=sim_cutoff):
                row = listings.iloc[idx_by_name[cand]]
                code = row["Code"]; key = row["Name"]
                counts.setdefault(key, {"code":code, "ticker":_kr_ticker(code), "hits":0,
                                        "sector":row["Sector"], "industry":row["Industry"]})
                counts[key]["hits"] += 1
    return counts

def _auto_build_theme_stocks(theme_rows_df: pd.DataFrame, news_all: List[dict],
                             top_per_theme: int = 6,
                             extra_kws: Dict[str, List[str]] | None = None) -> Dict[str, List[Tuple[str,str]]]:
    """
    테마별 대표 종목 자동 구성:
    - 뉴스→회사명 언급 집계
    - 회사명/섹터/산업 텍스트에 '테마명' 또는 사용자 추가 키워드 포함 시 후보
    - 언급수 상위 N개 반환
    """
    if theme_rows_df is None or theme_rows_df.empty:
        return {}

    listings = _load_krx_listings()
    mentions = _extract_company_mentions(news_all, listings)

    theme2stocks = {}
    for _, tr in theme_rows_df.iterrows():
        theme = str(tr["테마"])
        theme_kw = theme.lower()
        user_kws = [k.lower() for k in (extra_kws or {}).get(theme, [])]

        candidates = []
        for name, meta in mentions.items():
            blob = f"{name} {meta.get('sector','')} {meta.get('industry','')}".lower()
            if (theme_kw in blob) or any(k in blob for k in user_kws):
                if meta.get("ticker"):
                    candidates.append((name, meta["ticker"], meta["hits"]))
        # 정렬 + 티커 중복 제거
        candidates.sort(key=lambda x: x[2], reverse=True)
        seen = set(); uniq=[]
        for nm, tk, h in candidates:
            if tk in seen: continue
            seen.add(tk); uniq.append((nm, tk))
        theme2stocks[theme] = uniq[:top_per_theme]
    return theme2stocks

# -----------------------------
# 3) 유망 종목 추천
# -----------------------------
def _collect_all_news_for_3days() -> List[dict]:
    """모든 카테고리에서 3일치 호출(중복 포함)"""
    cats = ["경제뉴스","산업뉴스","정책뉴스"]
    out=[]
    for c in cats:
        out += fetch_category_news(c, days=3, max_items=120)
    return out

def _pick_promising(theme_rows_df: pd.DataFrame,
                    auto_theme_stocks: Dict[str, List[Tuple[str,str]]],
                    top_n: int = 5) -> pd.DataFrame:
    """뉴스빈도 + 등락률 기반 TopN 선별"""
    candidates=[]
    if theme_rows_df is None or theme_rows_df.empty:
        return pd.DataFrame()

    for _, tr in theme_rows_df.iterrows():
        theme = tr["테마"]
        count = int(tr["뉴스건수"])
        for name, tk in auto_theme_stocks.get(theme, []):
            last, prev = fetch_quote(tk)
            if not _valid_prices(last, prev):
                continue
            delta = (last - prev) / prev * 100
            score = count * 0.3 + delta * 0.7
            candidates.append({"테마":theme, "종목명":name, "티커":tk,
                               "등락률(%)": round(delta,2), "뉴스빈도": count,
                               "AI점수": round(score,2)})
    df = pd.DataFrame(candidates)
    return df.sort_values("AI점수", ascending=False).head(top_n) if not df.empty else df

def show_ai_recommendations(theme_rows_df: pd.DataFrame):
    """
    - 최근 3일 모든 카테고리 뉴스 수집
    - KRX 자동 매핑으로 테마별 대표 종목 구성
    - Top5 유망 종목 출력 + 간단 코멘트
    """
    st.markdown("## 🚀 오늘의 AI 유망 종목 Top5")

    all_news = _collect_all_news_for_3days()
    auto_theme_stocks = _auto_build_theme_stocks(theme_rows_df, all_news, top_per_theme=6)

    if not auto_theme_stocks:
        st.info("뉴스-종목 자동 매핑 결과가 부족합니다. 키워드를 넓혀보세요.")
        return

    rec_df = _pick_promising(theme_rows_df, auto_theme_stocks, top_n=5)
    if rec_df.empty:
        st.info("추천할 종목이 없습니다.")
        return

    st.dataframe(rec_df, use_container_width=True, hide_index=True)
    st.markdown("### 🧾 AI 종합 판단")
    for _, r in rec_df.iterrows():
        emoji = "🔺" if r["등락률(%)"] > 0 else "🔻"
        st.markdown(
            f"- **{r['종목명']} ({r['티커']})** — 테마: *{r['테마']}*, "
            f"등락률 **{r['등락률(%)']}%**, 뉴스빈도 {r['뉴스빈도']}건, AI점수 {r['AI점수']} {emoji}"
        )

# -----------------------------
# 4) (옵션) 3일 예측 모듈
# -----------------------------
@st.cache_data(ttl=900)
def _load_hist(ticker: str, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    return df[~df.index.duplicated(keep='last')].dropna()

def _rsi(series: pd.Series, period: int = 14):
    delta = series.diff()
    up = np.where(delta > 0, delta, 0.0)
    down = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(up, index=series.index).rolling(period).mean()
    roll_down = pd.Series(down, index=series.index).rolling(period).mean().replace(0, np.nan)
    rs = roll_up / roll_down
    r = 100 - (100 / (1 + rs))
    return r.fillna(50)

def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_f = series.ewm(span=fast, adjust=False).mean()
    ema_s = series.ewm(span=slow, adjust=False).mean()
    line  = ema_f - ema_s
    sig   = line.ewm(span=signal, adjust=False).mean()
    hist  = line - sig
    return line, sig, hist

def _build_features(df: pd.DataFrame):
    price = df["Close"]
    feat = pd.DataFrame(index=df.index)
    feat["ret_1d"] = price.pct_change(1)
    feat["ret_5d"] = price.pct_change(5)
    feat["ret_10d"] = price.pct_change(10)
    feat["vol_5d"] = price.pct_change().rolling(5).std()
    feat["vol_20d"] = price.pct_change().rolling(20).std()
    feat["rsi_14"] = _rsi(price, 14)
    m, s, h = _macd(price)
    feat["macd"] = m; feat["macd_sig"] = s; feat["macd_hist"] = h
    ma5 = price.rolling(5).mean(); ma20 = price.rolling(20).mean()
    feat["ma5_gap"] = (price - ma5) / ma5
    feat["ma20_gap"] = (price - ma20) / ma20
    y = (price.shift(-1) > price).astype(int)
    return pd.concat([feat, y.rename("y")], axis=1).dropna()

def predict_3day(tickers: List[str]) -> pd.DataFrame:
    """
    간단 로지스틱 회귀로 내일/3일 평균 상승확률 추정
    - 호출하는 쪽에서 표/코멘트 렌더링을 담당
    """
    rows=[]
    for tk in tickers:
        try:
            hist = _load_hist(tk)
            if hist is None or hist.empty:
                rows.append({"티커": tk, "내일상승확률": "-", "3일평균확률": "-", "신호":"데이터부족"})
                continue
            feats = _build_features(hist)
            if len(feats) < 120:
                rows.append({"티커": tk, "내일상승확률": "-", "3일평균확률": "-", "신호":"데이터부족"})
                continue
            data = feats.tail(300)
            X = data.drop(columns=["y"]).values
            y = data["y"].values
            n = len(data); split = max(60, n-3)
            X_train, y_train = X[:split], y[:split]
            X_pred = X[split:]
            model = LogisticRegression(max_iter=300)
            model.fit(X_train, y_train)
            prob = model.predict_proba(X_pred)[:,1]
            p1 = float(prob[0]) if len(prob)>0 else None
            p3 = float(prob.mean()) if len(prob)>0 else None
            if p1 is None:
                rows.append({"티커": tk, "내일상승확률": "-", "3일평균확률": "-", "신호":"데이터부족"})
            else:
                sig = "매수관심" if p1>=0.55 else ("관망" if p1>=0.45 else "주의")
                rows.append({"티커": tk, "내일상승확률": round(p1*100,1), "3일평균확률": round(p3*100,1), "신호": sig})
        except Exception:
            rows.append({"티커": tk, "내일상승확률": "-", "3일평균확률": "-", "신호":"오류"})
    return pd.DataFrame(rows)
