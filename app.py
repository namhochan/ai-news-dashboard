import pandas as pd
from modules.market import fetch_quote
from modules.news import THEME_STOCKS

def pick_promising_stocks(theme_rows, top_n: int = 5) -> pd.DataFrame:
    """
    테마당 1종목만 뽑아 Top N을 만든다.
    1) 각 테마에서 가격 조회 가능한 종목들 중 'AI점수 = 뉴스빈도*0.3 + 등락률*0.7'이 최고인 1종목 선별
    2) 선별된 테마 대표 종목들을 AI점수 내림차순으로 정렬 후 상위 N개 반환
    """
    best_per_theme = []

    for tr in theme_rows:
        # theme_rows의 키 호환 (영문/국문)
        theme = tr.get("테마") or tr.get("theme")
        news_cnt = tr.get("뉴스건수") or tr.get("count") or 0
        if not theme:
            continue

        stocks = THEME_STOCKS.get(theme, [])
        best = None  # (score, dict)

        for name, ticker in stocks:
            try:
                last, prev = fetch_quote(ticker)
                if not last or not prev:
                    continue
                delta_pct = (last - prev) / prev * 100.0
                score = news_cnt * 0.3 + delta_pct * 0.7
                row = {
                    "테마": theme,
                    "종목명": name,
                    "티커": ticker,
                    "등락률(%)": round(delta_pct, 2),
                    "뉴스빈도": int(news_cnt),
                    "AI점수": round(score, 2),
                }
                if (best is None) or (score > best[0]):
                    best = (score, row)
            except Exception:
                continue

        if best is not None:
            best_per_theme.append(best[1])

    if not best_per_theme:
        return pd.DataFrame(columns=["테마", "종목명", "티커", "등락률(%)", "뉴스빈도", "AI점수"])

    df = pd.DataFrame(best_per_theme).sort_values("AI점수", ascending=False).head(top_n)
    return df.reset_index(drop=True)
