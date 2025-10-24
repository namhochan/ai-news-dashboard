# -*- coding: utf-8 -*-
import pandas as pd
from .news import THEME_STOCKS
from .market import fetch_quote

def pick_promising_stocks_one_per_theme(theme_rows, top_n=5):
    """
    상위 테마에서 테마당 1종목씩 선발하여 TopN 구성.
    스코어 = 테마 뉴스빈도 30% + 개별 등락률 70%
    """
    if not theme_rows:
        return pd.DataFrame()

    candidates = []
    for tr in theme_rows[:max(5, top_n * 2)]:  # 상위 테마 충분히 보기
        theme = tr["테마"]
        count = tr["뉴스건수"]
        picked = None
        best_score = -1e9

        for name, ticker in THEME_STOCKS.get(theme, []):
            try:
                last, prev = fetch_quote(ticker)
                if not last or not prev: 
                    continue
                delta = (last - prev) / prev * 100.0
                score = count * 0.3 + delta * 0.7
                if score > best_score:
                    best_score = score
                    picked = {
                        "테마": theme,
                        "종목명": name,
                        "티커": ticker,
                        "등락률(%)": round(delta, 2),
                        "뉴스빈도": count,
                        "AI점수": round(score, 2),
                    }
            except Exception:
                continue

        if picked:
            candidates.append(picked)

    if not candidates:
        return pd.DataFrame()

    df = pd.DataFrame(candidates).sort_values(by="AI점수", ascending=False).drop_duplicates(subset=["테마"])
    return df.head(top_n).reset_index(drop=True)

def make_ai_commentary(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "<em>추천 결과가 없습니다.</em>"
    lines = []
    for _, r in df.iterrows():
        arrow = "🔺" if float(r["등락률(%)"]) >= 0 else "🔻"
        lines.append(
            f"- <b>{r['종목명']} ({r['티커']})</b> — 테마: <em>{r['테마']}</em>, "
            f"등락률: <b>{r['등락률(%)']}%</b>, 뉴스빈도: {int(r['뉴스빈도'])}건, AI점수: {r['AI점수']} {arrow}"
        )
    return "<br>".join(lines)
