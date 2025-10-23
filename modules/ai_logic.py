# modules/ai_logic.py
# -*- coding: utf-8 -*-
import re
import math
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from collections import Counter

# -----------------------------
# 간단 요약 + 키워드
# -----------------------------
def summarize_news(news_list, topn_kw=10, n_sent=5):
    """뉴스 리스트에서 키워드 TOPN 및 핵심 문장 N개 요약을 화면에 렌더링"""
    titles = [n.get("title", "") for n in news_list]
    descs = [n.get("desc", "") for n in news_list]
    texts = [f"{t} {d}" for t, d in zip(titles, descs)]

    # 키워드
    words = []
    for t in titles:
        t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t)
        words.extend([w for w in t.split() if len(w) >= 2])
    kw = [w for w, _ in Counter(words).most_common(topn_kw)]

    st.markdown("### 📌 핵심 키워드 TOP10")
    if kw:
        st.write(", ".join(kw))
    else:
        st.info("키워드 데이터가 부족합니다.")

    # 요약문
    full_text = " ".join(texts)
    sents = re.split(r'[.!?]\s+', full_text)
    sents = [s for s in sents if len(s.strip()) > 20]
    scores = {s: sum(word in full_text for word in s.split()) for s in sents}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    summary = [s for s, _ in ranked[:n_sent]]

    st.markdown("### 📰 핵심 요약문")
    if summary:
        st.markdown(f"**요약:** {summary[0][:150]}...")
        with st.expander("전체 요약문 보기 👇"):
            for s in summary:
                st.markdown(f"- {s.strip()}")
    else:
        st.info("요약 데이터를 가져오지 못했습니다.")


# -----------------------------
# 유망 종목 Top5 (뉴스강도 + 단기등락)
# -----------------------------
def _fmt_num(v, d=2):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:,.{d}f}"
    except Exception:
        return "-"

def _fmt_pct(v):
    try:
        if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
            return "-"
        return f"{v:+.2f}%"
    except Exception:
        return "-"

def _fetch_last_prev(ticker: str):
    """yfinance만 사용 (FDR 제거)"""
    try:
        t = yf.Ticker(ticker)
        last = getattr(t.fast_info, "last_price", None)
        prev = getattr(t.fast_info, "previous_close", None)
        if last and prev:
            return float(last), float(prev)
    except Exception:
        pass
    # fallback
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
        cl = df.get("Close")
        if cl is not None:
            cl = cl.dropna()
            if len(cl) >= 2:
                return float(cl.iloc[-1]), float(cl.iloc[-2])
            elif len(cl) == 1:
                return float(cl.iloc[-1]), None
    except Exception:
        pass
    return None, None

def show_ai_recommendations(theme_rows_df, top_n=5):
    """
    detect_themes 결과 DataFrame(theme_rows_df)을 받아
    뉴스강도(건수) + 당일 등락률을 합산해 Top N을 추천.
    theme_rows_df 컬럼 예시:
      - '테마' 또는 'theme'
      - '뉴스건수' 또는 'count'
      - '대표종목'(쉼표/중간점 분리), 혹은 'rep_stocks'(옵션)
    """
    if theme_rows_df is None or theme_rows_df.empty:
        st.info("추천을 생성할 테마 데이터가 없습니다.")
        return

    # 컬럼 유연하게 매핑
    cname_theme = "테마" if "테마" in theme_rows_df.columns else ("theme" if "theme" in theme_rows_df.columns else None)
    cname_count = "뉴스건수" if "뉴스건수" in theme_rows_df.columns else ("count" if "count" in theme_rows_df.columns else None)
    cname_rep   = "대표종목" if "대표종목" in theme_rows_df.columns else ("rep_stocks" if "rep_stocks" in theme_rows_df.columns else None)

    if cname_theme is None or cname_count is None:
        st.info("테마/뉴스건수 컬럼이 없어 추천을 생략합니다.")
        return

    # 상위 테마 몇 개만 사용
    base = theme_rows_df.sort_values(by=cname_count, ascending=False).head(8)

    candidates = []
    for _, r in base.iterrows():
        theme = str(r[cname_theme])
        rep = str(r[cname_rep]) if cname_rep else "-"
        # 대표종목 문자열 → [(이름,티커), ...] 로 추출 시도 (이름과 티커를 ‘공백/괄호/점’ 등으로 분리)
        pairs = []
        if rep and rep != "-" and rep != "nan":
            # 예: "삼성전자·SK하이닉스·DB하이텍"
            # 티커가 붙지 않은 경우는 스킵, 대신 하단에 이름만 표기
            for name in re.split(r"[·,|/]\s*", rep):
                name = name.strip()
                # 티커 추정 규칙이 없다면 생략
                pairs.append((name, None))

        # 만약 detect_themes 쪽에서 ticker 목록을 넣어주면 더 정확 (여기서는 안전하게 None 허용)
        # 가격/등락 계산은 티커가 있는 경우에만 진행
        stock_rows = []
        for name, ticker in pairs:
            if not ticker:
                continue
            last, prev = _fetch_last_prev(ticker)
            if last is None or prev in (None, 0):
                continue
            delta = (last - prev) / prev * 100.0
            stock_rows.append({
                "테마": theme,
                "종목명": name,
                "티커": ticker,
                "등락률(%)": round(delta, 2),
                "뉴스건수": int(r[cname_count])
            })

        # 티커가 없는 경우(대표종목 이름만 있을 때)는 후보에서 제외되지만,
        # 표시는 하단 설명문에서 “대표종목 이름 목록”으로 안내
        candidates.extend(stock_rows)

    df = pd.DataFrame(candidates)
    if df.empty:
        st.info("대표 종목의 티커가 없어 가격 기반 추천을 생성하지 못했습니다. (테마 표는 위에서 확인하세요)")
        return

    # 간단 스코어: 뉴스건수(0.3) + 등락률(0.7)
    df["AI점수"] = df["뉴스건수"] * 0.3 + df["등락률(%)"] * 0.7
    top = df.sort_values("AI점수", ascending=False).head(top_n)
    st.markdown("### 🚀 오늘의 AI 유망 종목 Top5")
    st.dataframe(top[["테마","종목명","티커","등락률(%)","뉴스건수","AI점수"]],
                 use_container_width=True, hide_index=True)

    st.markdown("### 🧾 AI 종합 판단")
    for _, row in top.iterrows():
        emoji = "🔺" if row["등락률(%)"] > 0 else "🔻"
        st.markdown(
            f"- **{emoji} {row['종목명']}** ({row['티커']}) — "
            f"테마: *{row['테마']}*, 최근 등락률 **{_fmt_pct(row['등락률(%)'])}**, "
            f"뉴스빈도: {int(row['뉴스건수'])}건, AI점수: {row['AI점수']:.2f}"
        )


# -----------------------------
# (옵션) 간단 3일 예측 — yfinance만 사용
# -----------------------------
def _load_hist_yf(ticker: str, period="2y"):
    df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
    df = df[~df.index.duplicated(keep="last")].dropna()
    return df

def predict_3day(tickers):
    """단순 피쳐 + 로지스틱(있으면), 없으면 확률 예측 생략."""
    try:
        from sklearn.linear_model import LogisticRegression
    except Exception:
        st.warning("scikit-learn이 설치되어 있지 않아 3일 예측을 생략합니다.")
        return pd.DataFrame()

    def rsi(series, n=14):
        delta = series.diff()
        up = np.where(delta > 0, delta, 0.0)
        down = np.where(delta < 0, -delta, 0.0)
        ru = pd.Series(up, index=series.index).rolling(n).mean()
        rd = pd.Series(down, index=series.index).rolling(n).mean()
        rs = ru / rd.replace(0, np.nan)
        return (100 - 100/(1+rs)).fillna(50)

    def macd(series, fast=12, slow=26, signal=9):
        ema_f = series.ewm(span=fast, adjust=False).mean()
        ema_s = series.ewm(span=slow, adjust=False).mean()
        m = ema_f - ema_s
        s = m.ewm(span=signal, adjust=False).mean()
        h = m - s
        return m, s, h

    rows = []
    for tkr in tickers:
        try:
            df = _load_hist_yf(tkr)
            px = df["Close"]
            feat = pd.DataFrame(index=df.index)
            feat["r1"] = px.pct_change(1)
            feat["r5"] = px.pct_change(5)
            feat["vol5"] = px.pct_change().rolling(5).std()
            feat["rsi14"] = rsi(px, 14)
            m, s, h = macd(px)
            feat["macd"] = m; feat["macd_sig"] = s; feat["macd_h"] = h
            ma5 = px.rolling(5).mean(); ma20 = px.rolling(20).mean()
            feat["gap5"] = (px - ma5) / ma5
            feat["gap20"] = (px - ma20) / ma20
            y = (px.shift(-1) > px).astype(int)
            data = pd.concat([feat, y.rename("y")], axis=1).dropna()
            if len(data) < 120:
                rows.append({"티커": tkr, "내일상승확률": "-", "3일평균확률": "-", "신호": "데이터부족"})
                continue
            X = data.drop(columns=["y"]).values
            yv = data["y"].values
            n = len(data); split = max(60, n-3)
            model = LogisticRegression(max_iter=200)
            model.fit(X[:split], yv[:split])
            prob = model.predict_proba(X[split:])[:,1]
            p1 = float(prob[0]) if len(prob)>0 else None
            p3 = float(prob.mean()) if len(prob)>0 else None
            sig = "매수관심" if (p1 or 0) >= 0.55 else ("관망" if (p1 or 0) >= 0.45 else "주의")
            rows.append({"티커": tkr,
                         "내일상승확률": None if p1 is None else round(p1*100,1),
                         "3일평균확률": None if p3 is None else round(p3*100,1),
                         "신호": sig})
        except Exception:
            rows.append({"티커": tkr, "내일상승확률": "-", "3일평균확률": "-", "신호": "오류"})
    return pd.DataFrame(rows)
