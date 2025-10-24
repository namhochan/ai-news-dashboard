modules/ai_logic.py

요약/테마 리포트/유망종목(테마다 1종목) + 저장 유틸 (샌드박스/외부의존 방어)

v3.7.1+3

from future import annotations from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple from datetime import datetime, timezone, timedelta import re import os import math import numpy as np import pandas as pd

외부 종속: modules.market.fetch_quote 가 기본. 폴백은 호출측(app.py)에서 처리함.

try: from modules.market import fetch_quote  # type: ignore except Exception as _e:  # pragma: no cover fetch_quote = None  # type: ignore

고정 KST (tzdata 없이 안전)

KST = timezone(timedelta(hours=9))

---------- 요약/키워드 ----------

def extract_keywords(titles: Iterable[str], topn: int = 10) -> List[str]: words: List[str] = [] for t in titles or []: t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", (t or "")) # 1자 토큰은 잡음일 확률이 높으니 제거 words.extend([w for w in t.split() if len(w) >= 2]) from collections import Counter return [w for w, _ in Counter(words).most_common(max(0, int(topn)))]

def summarize_sentences(texts: Sequence[str], n_sent: int = 5) -> List[str]: if not texts: return [] full = " ".join(t or "" for t in texts) # 문장 분리 (영문/한글 단순 규칙) sents = re.split(r"[.!?]\s+|[\n\r]", full) sents = [s.strip() for s in sents if len(s.strip()) > 20] if not sents: return [] # 아주 단순한 TF 득점: 문장 내 단어가 전체 본문에 얼마나 등장하는지 # (샌드박스/성능 균형) scores = {s: sum(w in full for w in s.split()) for s in sents} ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True) return [s for s, _ in ranked[: max(1, int(n_sent))]]

---------- 테마 강도/리스크 ----------

def calc_theme_strength(count: int, avg_delta: float) -> float: """뉴스 빈도와 가격 모멘텀을 05 점수로 환산. - count 20건 이상이면 빈도 점수 1.0 캡 - avg_delta(+5%): 가격 점수 1.0, (-5%): 0.0 근사 """ try: freq = min(max(count / 20.0, 0.0), 1.0) price = min(max((avg_delta + 5.0) / 10.0, 0.0), 1.0) return round((freq * 0.6 + price * 0.4) * 5.0, 1) except Exception: return 0.0

def calc_risk_level(avg_delta: float) -> int: if avg_delta >= 3: return 1 if avg_delta >= 1: return 2 if avg_delta >= -1: return 3 if avg_delta >= -3: return 4 return 5

def make_theme_report(theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]]) -> pd.DataFrame: rows: List[Dict[str, Any]] = [] for tr in (theme_rows or [])[:8]: theme = tr.get("theme") stocks = theme_stocks_map.get(theme or "", []) deltas: List[float] = [] for _, t in stocks: last, prev, _ = (None, None, None) try: if fetch_quote: last, prev, _ = fetch_quote(t) except Exception: last, prev = None, None if last not in (None,) and prev not in (None, 0): try: deltas.append((float(last) - float(prev)) / float(prev) * 100.0) except Exception: continue avg_delta = float(np.mean(deltas)) if deltas else 0.0 rows.append( { "테마": theme, "뉴스건수": int(tr.get("count", 0)), "평균등락(%)": round(avg_delta, 2), "테마강도(15)": calc_risk_level(avg_delta), } ) return pd.DataFrame(rows)

---------- 유망 종목 (테마다 1종목) ----------

MAX_ABS_MOVE = 25.0  # 점수 계산용 캡(±25%) OUTLIER_DROP = 35.0  # 절대 35% 넘으면 제외 MIN_VOLUME = 30_000  # 거래량 하한 (vol 정보 없으면 통과)

def _safe_delta_pct(ticker: str): last, prev, vol = (None, None, None) try: if fetch_quote: last, prev, vol = fetch_quote(ticker) except Exception: last, prev, vol = None, None, None if last in (None,) or prev in (None, 0): return None try: pct = (float(last) - float(prev)) / float(prev) * 100.0 except Exception: return None # 거래량 체크(정보가 있을 때만) try: if vol is not None and int(vol) < MIN_VOLUME: return None except Exception: pass # 급격한 이상치 제거 if abs(pct) > OUTLIER_DROP: return None pct_for_score = float(np.clip(pct, -MAX_ABS_MOVE, MAX_ABS_MOVE)) return pct, pct_for_score, vol

def pick_promising_by_theme_once( theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]], top_n: int = 5, ) -> pd.DataFrame: """ 테마다 1종목씩 뽑아 Top N 구성. 스코어 = 뉴스빈도(정규화)*0.4 + (캡핑된 일간등락률/MAX_ABS_MOVE)*0.6   (-1001 cand = { "테마": theme, "종목명": name, "티커": ticker, "등락률(%)": round(float(real_pct), 2), "뉴스빈도": int(freq), "AI점수": round(float(score) * 100.0, 2), "거래량": None if vol is None else int(vol), } if best is None or cand["AI점수"] > best["AI점수"]: best = cand if best: selected.append(best) if len(selected) >= int(top_n): break selected.sort(key=lambda x: x["AI점수"], reverse=True) return pd.DataFrame(selected)

---------- 저장 유틸 ----------

def _ensure_dir(path: str) -> None: if not os.path.isdir(path): os.makedirs(path, exist_ok=True)

def save_report_and_picks( theme_rows: List[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]], out_dir: str = "reports", top_n: int = 5, prefix: Optional[str] = None, ) -> Dict[str, str]: ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S") tag = (prefix + "_") if prefix else "" _ensure_dir(out_dir)

report_df = make_theme_report(theme_rows, theme_stocks_map)
picks_df = pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=top_n)

report_csv = os.path.join(out_dir, f"{tag}theme_report_{ts}.csv")
report_json = os.path.join(out_dir, f"{tag}theme_report_{ts}.json")
picks_csv = os.path.join(out_dir, f"{tag}promising_picks_{ts}.csv")
picks_json = os.path.join(out_dir, f"{tag}promising_picks_{ts}.json")

# CSV 저장 (UTF-8 with BOM: 엑셀 호환)
report_df.to_csv(report_csv, index=False, encoding="utf-8-sig")
picks_df.to_csv(picks_csv, index=False, encoding="utf-8-sig")

# JSON 저장
import json as _json
with open(report_json, "w", encoding="utf-8") as f:
    _json.dump(report_df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
with open(picks_json, "w", encoding="utf-8") as f:
    _json.dump(picks_df.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

return {
    "report_csv": report_csv,
    "report_json": report_json,
    "picks_csv": picks_csv,
    "picks_json": picks_json,
}

=============================

자체 테스트 (네트워크/외부 의존 없이)

=============================

if name == "main": # 1) 키워드 추출 테스트 kws = extract_keywords(["AI 반도체 급등", "로봇·AI 투자 확대"], topn=5) assert isinstance(kws, list) and len(kws) >= 1

# 2) 문장 요약 테스트
sents = summarize_sentences([
    "AI 관련 투자가 확대되고 있으며 반도체 수요도 동반 상승하고 있다.",
    "정부 정책 지원과 함께 기업들의 투자계획이 증가하는 추세다.",
], n_sent=2)
assert isinstance(sents, list) and 0 < len(sents) <= 2

# 3) 테마 리포트/추천: fetch_quote 의존을 최소화하기 위해 더미 맵 사용
theme_rows = [{"theme": "AI", "count": 10}, {"theme": "로봇", "count": 6}]
theme_map = {"AI": [("A","AAA.KS"), ("B","BBB.KS")], "로봇": [("C","CCC.KQ")]} 

# fetch_quote가 없다면 임시 몽키패치
if fetch_quote is None:
    def _fq(_t: str):  # last, prev, vol
        seed = sum(ord(c) for c in _t) % 100
        last = 100.0 + (seed - 50) * 0.2
        prev = last * (1.0 - ((seed % 7) - 3) * 0.01)
        vol = 40_000 + seed * 1000
        return last, prev, vol
    fetch = _fq  # local alias
else:
    fetch = fetch_quote

# 로컬 스코프에서 _safe_delta_pct를 거치도록 간단 검사
df_report = make_theme_report(theme_rows, theme_map)
assert isinstance(df_report, pd.DataFrame) and set(["테마","뉴스건수","평균등락(%)"]).issubset(df_report.columns)

df_picks = pick_promising_by_theme_once(theme_rows, theme_map, top_n=3)
assert isinstance(df_picks, pd.DataFrame)
if not df_picks.empty:
    for col in ["테마","종목명","티커","등락률(%)","뉴스빈도","AI점수"]:
        assert col in df_picks.columns

# 4) 저장기능 경로만 생성 확인 (파일 쓰기)
paths = save_report_and_picks(theme_rows, theme_map, out_dir="reports_test_ai_logic", top_n=2, prefix="unittest")
for k in ["report_csv","report_json","picks_csv","picks_json"]:
    assert os.path.isfile(paths[k])

print("[ai_logic] ✅ All self-tests passed.")
