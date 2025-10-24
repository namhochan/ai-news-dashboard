-- coding: utf-8 --

""" modules/ai_logic.py – 요약/테마 리포트/유망종목(테마다 1종목) + 저장 유틸 Streamlit 안전 버전 v3.7.1+R

외부 의존:

pandas, numpy (requirements.txt에 포함)

시세는 modules.market.fetch_quote 에 위임 (yfinance 유무/네트워크는 market 모듈이 방어) """


from future import annotations from typing import List, Dict, Any, Iterable, Optional, Tuple import re from collections import Counter import numpy as np import pandas as pd from datetime import datetime, timezone, timedelta import os import json

내부 시세 유틸

try: from modules.market import fetch_quote  # last, prev, vol from modules.market import fmt_number, fmt_percent except Exception:  # pragma: no cover - 임포트 실패 시 더미 제공 def fetch_quote(_ticker: str): return None, None, None def fmt_number(v, d=2): try: return f"{float(v):.{d}f}" except Exception: return "-" def fmt_percent(v): try: return f"{float(v):+.2f}%" except Exception: return "-"

안전한 KST (tzdata 불요)

KST = timezone(timedelta(hours=9))

---------------------- 키워드/요약 ----------------------

def extract_keywords(titles: Iterable[str], topn: int = 10) -> List[str]: """아주 간단한 빈도 기반 키워드 추출(한/영/숫자, 길이≥2).""" words: List[str] = [] for t in titles or []: t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", t or "") words.extend([w for w in t.split() if len(w) >= 2]) return [w for w, _ in Counter(words).most_common(max(1, int(topn)))]

def summarize_sentences(texts: Iterable[str], n_sent: int = 5) -> List[str]: """아주 단순한 중요도 점수 기반 문장 요약. - 문장 분리는 .!? 기준, 길이>20자만 사용 - 점수는 전체 텍스트에서 단어 존재 횟수의 합 """ texts = list(texts or []) if not texts: return [] full = " ".join(texts) sents = re.split(r"[.!?]\s+", full) sents = [s.strip() for s in sents if len(s.strip()) > 20] if not sents: return [] scores = {s: sum((w in full) for w in s.split()) for s in sents} ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True) return [s for s, _ in ranked[: max(1, int(n_sent))]]

---------------------- 테마 지표 ----------------------

def calc_theme_strength(count: int, avg_delta: float) -> float: """테마강도 1~5 (빈도 0.6 + 가격 0.4). avg_delta: %""" try: freq = min(max(float(count) / 20.0, 0.0), 1.0) price = min(max((float(avg_delta) + 5.0) / 10.0, 0.0), 1.0) return round((freq * 0.6 + price * 0.4) * 5.0, 1) except Exception: return 0.0

def calc_risk_level(avg_delta: float) -> int: try: a = float(avg_delta) except Exception: a = 0.0 if a >= 3: return 1 if a >= 1: return 2 if a >= -1: return 3 if a >= -3: return 4 return 5

---------------------- 테마 리포트 ----------------------

def make_theme_report(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]]) -> pd.DataFrame: """뉴스에서 감지한 테마들과 대표 종목들의 평균 등락률/강도/리스크 산출. theme_rows: [{"theme": str, "count": int, ...}] theme_stocks_map: { theme: [(name, ticker), ...] } """ rows: List[Dict[str, Any]] = [] for tr in (theme_rows or [])[:8]: theme = tr.get("theme") if not theme: continue stocks = theme_stocks_map.get(theme, []) deltas: List[float] = [] for _, t in stocks: last, prev, _ = fetch_quote(t) if last and prev: try: deltas.append((float(last) - float(prev)) / float(prev) * 100.0) except Exception: pass avg_delta = float(np.mean(deltas)) if deltas else 0.0 rows.append( { "테마": theme, "뉴스건수": int(tr.get("count", 0)), "평균등락(%)": round(avg_delta, 2), "테마강도(15)": calc_risk_level(avg_delta), } ) return pd.DataFrame(rows)

---------------------- 유망 종목 선정 ----------------------

점수 계산용 파라미터 (과격값 방지)

MAX_ABS_MOVE = 25.0     # ±25% 캡 OUTLIER_DROP = 35.0     # |등락|>35% 제외 MIN_VOLUME   = 30_000   # 거래량 하한(정보 없으면 통과)

def _safe_delta_pct(ticker: str): last, prev, vol = fetch_quote(ticker) if not last or not prev: return None try: pct = (float(last) - float(prev)) / float(prev) * 100.0 except Exception: return None # 거래량 체크(정보가 있을 때만) if vol is not None and vol < MIN_VOLUME: return None # 급격한 이상치 제거 if abs(pct) > OUTLIER_DROP: return None pct_for_score = float(np.clip(pct, -MAX_ABS_MOVE, MAX_ABS_MOVE)) return pct, pct_for_score, vol

def pick_promising_by_theme_once(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]], top_n: int = 5) -> pd.DataFrame: """테마다 1종목씩 뽑아 Top N 구성. 스코어 = 뉴스빈도(정규화)*0.4 + (캡핑된 일간등락률/MAX_ABS_MOVE)*0.6  (-1001 cand = { "테마": theme, "종목명": name, "티커": ticker, "등락률(%)": round(float(real_pct), 2), "뉴스빈도": freq, "AI점수": round(score * 100.0, 2), "거래량": vol, } if best is None or cand["AI점수"] > best["AI점수"]: best = cand if best: selected.append(best) if len(selected) >= int(top_n): break selected.sort(key=lambda x: x["AI점수"], reverse=True) return pd.DataFrame(selected)

---------------------- 저장 유틸 ----------------------

def save_report_and_picks(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]], out_dir: str = "reports", top_n: int = 5, prefix: str = "export") -> Dict[str, str]: """테마 raw(rows)와 유망종목(계산)을 CSV/JSON으로 저장. 경로 사전 반환.""" os.makedirs(out_dir, exist_ok=True) ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")

# 테마 리포트 저장 (rows 그대로 저장: DataFrame으로도 저장)
report_csv = os.path.join(out_dir, f"{prefix}_theme_report_{ts}.csv")
report_json = os.path.join(out_dir, f"{prefix}_theme_report_{ts}.json")
try:
    pd.DataFrame(theme_rows).to_csv(report_csv, index=False, encoding="utf-8")
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(theme_rows, f, ensure_ascii=False, indent=2)
except Exception:
    # 경로 쓰기 실패 등은 상위에서 메시지 처리
    pass

# 유망 종목 저장
picks_df = pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=top_n)
picks_csv = os.path.join(out_dir, f"{prefix}_promising_picks_{ts}.csv")
picks_json = os.path.join(out_dir, f"{prefix}_promising_picks_{ts}.json")
try:
    if not picks_df.empty:
        picks_df.to_csv(picks_csv, index=False, encoding="utf-8")
        with open(picks_json, "w", encoding="utf-8") as f:
            json.dump(picks_df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    else:
        # 빈 파일도 생성하여 경로 반환 일관성 유지
        open(picks_csv, "a", encoding="utf-8").close()
        open(picks_json, "a", encoding="utf-8").close()
except Exception:
    pass

return {
    "report_csv": report_csv,
    "report_json": report_json,
    "picks_csv": picks_csv,
    "picks_json": picks_json,
}

---------------------- 간단 테스트 ----------------------

if name == "main":  # 기본 동작 확인용 (Streamlit 실행에는 영향 없음) # 1) 키워드/요약 테스트 titles = [ "AI 반도체 수요 급증으로 HBM 투자 확대", "로봇 산업 정책 지원 강화", "데이터센터 전력요금 인상 논의", ] print("keywords:", extract_keywords(titles, topn=5)) print("summary:", summarize_sentences(titles, n_sent=2))

# 2) 테마 리포트 기본 경로 (빈 종목맵으로도 오류 없이 동작)
theme_rows = [
    {"theme": "AI", "count": 12},
    {"theme": "로봇", "count": 7},
]
theme_stocks_map = {"AI": [("삼성전자", "005930.KS")]}
df = make_theme_report(theme_rows, theme_stocks_map)
print("theme_report shape:", df.shape)

# 3) 유망 선정(빈 시세 환경에서도 안전 반환)
picks = pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=5)
print("picks rows:", len(picks))

# 4) 저장 유틸 경로 반환 테스트
paths = save_report_and_picks(theme_rows, theme_stocks_map, out_dir="reports", top_n=3, prefix="test")
print("saved:", paths)
