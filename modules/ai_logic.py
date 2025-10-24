# modules/ai_logic.py
# 요약/테마 리포트/유망종목(테마다 1종목) 선택 로직 – V3.7.1+R 확장(“+3”) 저장 기능 포함
# ───────────────────────────────────────────────────────────
# 목표
# 1) 외부 의존성(특히 modules.market.fetch_quote) 부재 시에도 동작하는 폴백 제공 (기존 유지)
# 2) V3.7.1+R 고정 규격에 맞춰 **AI 리스크 레벨**과 **테마강도(1~5)** 해석/전략 텍스트를 자동 포함
# 3) CLI/샌드박스에서 **CSV/JSON 저장 기능** 제공 (보고서 & 유망종목 Top-N)
# 4) 테스트 케이스 포함 (단독 실행 검증)
# ───────────────────────────────────────────────────────────

from __future__ import annotations
import os
import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

KST = ZoneInfo("Asia/Seoul")

# ===== 0) fetch_quote 폴백 =====
# 기대 반환: (last_price: float|None, prev_close: float|None, volume_or_meta)
try:
    from modules.market import fetch_quote as _fetch_quote_market  # type: ignore
    def _fetch_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Any]:  # pragma: no cover
        return _fetch_quote_market(ticker)
except Exception:  # ImportError 등
    def _fetch_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Any]:
        # 간단한 시뮬레이션: 티커 해시 기반으로 약간의 변동과 거래량 생성
        seed = sum(ord(c) for c in ticker) % 100
        last = 100.0 + (seed - 50) * 0.2
        prev = last * (1.0 - ((seed % 7) - 3) * 0.005)
        volume = 50_000 + (seed * 800)
        return float(last), float(prev), int(volume)

# ===== 1) 요약/키워드 =====

def extract_keywords(titles: Sequence[str], topn: int = 10) -> List[str]:
    """제목 리스트에서 단순 빈도 기반 키워드 Top-N 추출.
    - 영문/숫자/한글만 남기고 2글자 이상 토큰만 사용
    """
    words: List[str] = []
    for t in titles:
        t = re.sub(r"[^가-힣A-Za-z0-9\s]", " ", (t or ""))
        words.extend(w for w in t.split() if len(w) >= 2)
    return [w for w, _ in Counter(words).most_common(max(0, int(topn)))]


def summarize_sentences(texts: Sequence[str], n_sent: int = 5) -> List[str]:
    """아주 단순한 문장 중요도 점수로 상위 n_sent 문장 반환.
    - 문장 분리: 마침표/물음표/느낌표 기준
    - 스코어: 각 문장 토큰이 전체 텍스트에 등장하는지 카운트
    - 20자 미만 문장은 제외
    """
    if not texts:
        return []
    full = " ".join(texts)
    sents = re.split(r'[.!?]\s+', full)
    sents = [s.strip() for s in sents if len(s.strip()) > 20]
    scores = {s: sum((w in full) for w in s.split()) for s in sents}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [s for s, _ in ranked[: max(0, int(n_sent))]]


# ===== 2) V3.7.1+R: 테마 강도/리스크 (해석/전략 텍스트 포함) =====
# 수치 계산은 단순 정규화, 해석은 고정 테이블 매핑

# (필터/스코어에서 사용할 상수는 아래 3) 섹션에 존재)

_V371R_RISK_MAP: Dict[int, Dict[str, str]] = {
    1: {
        "name": "Level 1 – 매우 낮음",
        "price_action": "완만한 상승 추세 유지, 변동성 낮음",
        "supply_demand": "수급 균형 양호, 외인/기관 동반 순매수 가능성",
        "strategy": "추세 추종 분할매수, 단기 눌림 매수 유효",
        "alert": "급등 과열 구간 진입 신호 모니터링",
        "final": "BUY/ACCUMULATE"
    },
    2: {
        "name": "Level 2 – 낮음",
        "price_action": "상승 우위이나 조정 혼재",
        "supply_demand": "순매수 우위이나 구간별 차익 매물 소화",
        "strategy": "분할/눌림 매수, 이익실현 1차 분할",
        "alert": "뉴스 변수/갭 리스크 주의",
        "final": "BUY/HOLD"
    },
    3: {
        "name": "Level 3 – 중립",
        "price_action": "박스권/변동성 확대 구간",
        "supply_demand": "수급 혼조, 개인 비중 확대 가능",
        "strategy": "보유자는 홀드, 신규는 뉴스 모멘텀 확인 후 소량",
        "alert": "지지선 이탈 시 손절 규칙 철저",
        "final": "HOLD/SELECTIVE"
    },
    4: {
        "name": "Level 4 – 높음",
        "price_action": "하락 압력/데드캣 바운스 반복",
        "supply_demand": "순매도 우위, 유동성 얇음",
        "strategy": "단기 트레이딩 위주, 보수적 접근",
        "alert": "갭 하락/뉴스 악재 즉시 대응",
        "final": "AVOID/TRADE ONLY"
    },
    5: {
        "name": "Level 5 – 매우 높음",
        "price_action": "급락/과변동 구간",
        "supply_demand": "수급 급격 악화, 신용/반대매매 리스크",
        "strategy": "관망 또는 초단타, 레버리지 금지",
        "alert": "손절 트리거 강화, 포지션 최소화",
        "final": "AVOID"
    },
}

_V371R_THEME_STRENGTH_MAP: Dict[int, Dict[str, str]] = {
    1: {"name": "약함(1)", "interpret": "초기 탐색 단계, 뉴스 빈도/가격 반응 미약", "playbook": "관심종목 등록, 저위험 탐색"},
    2: {"name": "보통 이하(2)", "interpret": "조용한 누적/대기", "playbook": "저점 매수 관망, 뉴스 촉발 대기"},
    3: {"name": "보통(3)", "interpret": "본격 매집 초입/확인 구간", "playbook": "분할 접근, 리스크 관리 병행"},
    4: {"name": "강함(4)", "interpret": "확장 매집/가속", "playbook": "추세 추종, 분할 익절 트레일링"},
    5: {"name": "매우 강함(5)", "interpret": "분출/분배 국면 가능", "playbook": "단기 과열 경계, 익절 우선"},
}


def calc_theme_strength(count: int, avg_delta: float) -> float:
    """뉴스 빈도와 평균 등락률을 0~1로 정규화 후 가중합 → 1~5 스케일."""
    freq = min(max(count / 20.0, 0.0), 1.0)
    price = min(max((avg_delta + 5) / 10.0, 0.0), 1.0)
    return round((freq * 0.6 + price * 0.4) * 5.0, 1)


def calc_risk_level(avg_delta: float) -> int:
    """평균 등락률 기반의 단순 리스크 지표(1=최저, 5=최고)."""
    if avg_delta >= 3:
        return 1
    if avg_delta >= 1:
        return 2
    if avg_delta >= -1:
        return 3
    if avg_delta >= -3:
        return 4
    return 5


def _map_strength_level(value_1_to_5: float) -> int:
    # 반올림하여 1~5 정수 레벨로 변환
    v = int(round(float(value_1_to_5)))
    return min(5, max(1, v))


def make_theme_report(theme_rows: Sequence[Dict[str, Any]], theme_stocks_map: Dict[str, List[Tuple[str, str]]]) -> pd.DataFrame:
    """테마별 평균 등락, 강도, 리스크, 해석/전략 텍스트를 포함한 리포트 DataFrame 반환 (V3.7.1+R)."""
    rows: List[Dict[str, Any]] = []
    for tr in list(theme_rows)[:8]:
        theme = tr.get("theme")
        if theme is None:
            continue
        stocks = theme_stocks_map.get(theme, [])
        deltas: List[float] = []
        for _, t in stocks:
            last, prev, _ = _fetch_quote(t)
            if last is not None and prev not in (None, 0):
                deltas.append((last - prev) / prev * 100.0)
        avg_delta = float(np.mean(deltas)) if deltas else 0.0
        strength_val = calc_theme_strength(int(tr.get("count", 0)), avg_delta)
        strength_lvl = _map_strength_level(strength_val)
        risk_lvl = calc_risk_level(avg_delta)
        strength_meta = _V371R_THEME_STRENGTH_MAP[strength_lvl]
        risk_meta = _V371R_RISK_MAP[risk_lvl]
        rows.append(
            {
                "테마": theme,
                "뉴스건수": tr.get("count", 0),
                "평균등락(%)": round(avg_delta, 2),
                "테마강도(1~5)": strength_val,
                "테마강도레벨": strength_meta["name"],
                "테마해석": strength_meta["interpret"],
                "테마전략": strength_meta["playbook"],
                "AI리스크(1~5)": risk_lvl,
                "리스크레벨": risk_meta["name"],
                "가격해석": risk_meta["price_action"],
                "수급해석": risk_meta["supply_demand"],
                "전략": risk_meta["strategy"],
                "알림조건": risk_meta["alert"],
                "최종판단": risk_meta["final"],
            }
        )
    return pd.DataFrame(rows)


# ===== 3) 유망 종목 (테마다 1종목) =====
# (필터 완화) 거래량 30,000주 이상만 필터링, 이상치 제거 한도 상향
MAX_ABS_MOVE: float = 25.0     # 점수 계산용 캡(±25%)
OUTLIER_DROP: float = 35.0     # 절대 35% 넘으면 제외
MIN_VOLUME: int   = 30_000     # 거래량 하한 (vol 정보 없으면 통과)


def _safe_delta_pct(ticker: str) -> Optional[Tuple[float, float, Optional[float]]]:
    """티커의 실제 등락률, 점수용 캡핑 등락률, 거래량을 반환. 필터 조건 미충족 시 None."""
    last, prev, vol = _fetch_quote(ticker)
    if last in (None,) or prev in (None, 0):
        return None
    pct = (last - prev) / prev * 100.0
    # 거래량 체크 (정보가 있을 때만)
    if vol is not None and isinstance(vol, (int, float)) and vol < MIN_VOLUME:
        return None
    # 급격한 이상치 제거
    if abs(pct) > OUTLIER_DROP:
        return None
    pct_for_score = float(np.clip(pct, -MAX_ABS_MOVE, MAX_ABS_MOVE))
    return float(pct), pct_for_score, (float(vol) if isinstance(vol, (int, float)) else None)


def pick_promising_by_theme_once(
    theme_rows: Sequence[Dict[str, Any]],
    theme_stocks_map: Dict[str, List[Tuple[str, str]]],
    top_n: int = 5,
) -> pd.DataFrame:
    """테마다 1종목씩 선별해 Top-N 구성 (V3.7.1+R 점수 스케일 유지).
    스코어 = 뉴스빈도(정규화)*0.4 + (캡핑된 일간등락률/MAX_ABS_MOVE)*0.6  →  -1~1 범위 → x100 점수화
    반환: [종목명, 티커, 테마, 등락률(%), 뉴스빈도, AI점수, 거래량] 컬럼의 DataFrame
    """
    selected: List[Dict[str, Any]] = []
    for tr in theme_rows:
        theme = tr.get("theme")
        if theme is None:
            continue
        freq = int(tr.get("count", 0))
        best: Optional[Dict[str, Any]] = None
        for name, ticker in theme_stocks_map.get(theme, []):
            res = _safe_delta_pct(ticker)
            if res is None:
                continue
            real_pct, score_pct, vol = res
            freq_score = min(max(freq / 20.0, 0.0), 1.0)
            score = freq_score * 0.4 + (score_pct / MAX_ABS_MOVE) * 0.6  # -1~1
            cand = {
                "테마": theme,
                "종목명": name,
                "티커": ticker,
                "등락률(%)": round(real_pct, 2),
                "뉴스빈도": freq,
                "AI점수": round(score * 100.0, 2),
                "거래량": vol,
            }
            if best is None or cand["AI점수"] > best["AI점수"]:
                best = cand
        if best:
            selected.append(best)
        if len(selected) >= max(1, int(top_n)):
            break
    selected.sort(key=lambda x: x["AI점수"], reverse=True)
    return pd.DataFrame(selected)


# ===== 4) 저장(보고서 & 추천) 유틸 =====

def _ensure_dir(path: str) -> None:
    if not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)


def save_report_and_picks(
    theme_rows: Sequence[Dict[str, Any]],
    theme_stocks_map: Dict[str, List[Tuple[str, str]]],
    out_dir: str = "reports",
    top_n: int = 5,
    prefix: Optional[str] = None,
) -> Dict[str, str]:
    """V3.7.1+R 해석 포함 테마 리포트와 유망종목을 CSV/JSON으로 저장하고 파일 경로를 반환.
    반환 keys: report_csv, report_json, picks_csv, picks_json
    """
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    tag = (prefix + "_") if prefix else ""
    _ensure_dir(out_dir)

    df_report = make_theme_report(theme_rows, theme_stocks_map)
    df_picks = pick_promising_by_theme_once(theme_rows, theme_stocks_map, top_n=top_n)

    report_csv = os.path.join(out_dir, f"{tag}theme_report_{ts}.csv")
    report_json = os.path.join(out_dir, f"{tag}theme_report_{ts}.json")
    picks_csv  = os.path.join(out_dir, f"{tag}promising_picks_{ts}.csv")
    picks_json = os.path.join(out_dir, f"{tag}promising_picks_{ts}.json")

    df_report.to_csv(report_csv, index=False, encoding="utf-8-sig")
    df_picks.to_csv(picks_csv, index=False, encoding="utf-8-sig")

    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(df_report.to_dict(orient="records"), f, ensure_ascii=False, indent=2)
    with open(picks_json, "w", encoding="utf-8") as f:
        json.dump(df_picks.to_dict(orient="records"), f, ensure_ascii=False, indent=2)

    return {
        "report_csv": report_csv,
        "report_json": report_json,
        "picks_csv": picks_csv,
        "picks_json": picks_json,
    }


# ===== 5) 간단 자체 테스트 (단독 실행용) =====
# 기존 테스트 케이스에 저장 기능 검증을 추가.

@dataclass
class _ThemeRow:
    theme: str
    count: int

if __name__ == "__main__":
    # --- 테스트 데이터 준비 ---
    THEME_ROWS = [
        {"theme": "AI", "count": 12},
        {"theme": "로봇", "count": 9},
        {"theme": "데이터센터", "count": 7},
    ]
    THEME_STOCKS = {
        "AI": [("솔루스첨단소재", "336370.KS"), ("삼성전자", "005930.KS")],
        "로봇": [("나우로보틱스", "277810.KQ"), ("유진로봇", "056080.KQ")],
        "데이터센터": [("삼성SDS", "018260.KS"), ("효성중공업", "298040.KS")],
    }

    # --- extract_keywords ---
    kw = extract_keywords(["삼성 AI 반도체 공급 확대", "AI 데이터센터 투자 확대"], topn=5)
    assert isinstance(kw, list) and len(kw) >= 1, "extract_keywords 실패"

    # --- summarize_sentences ---
    summ = summarize_sentences([
        "AI 데이터센터 투자가 확대되고 있습니다. 이는 반도체 수요 증가로 이어질 전망입니다.",
        "정부 정책 역시 관련 산업에 우호적으로 작용하고 있습니다."
    ], n_sent=2)
    assert isinstance(summ, list) and 0 <= len(summ) <= 2, "summarize_sentences 실패"

    # --- make_theme_report (V3.7.1+R 해석 포함) ---
    df_report = make_theme_report(THEME_ROWS, THEME_STOCKS)
    required_cols = {"테마","뉴스건수","평균등락(%)","테마강도(1~5)","테마강도레벨","테마해석","테마전략","AI리스크(1~5)","리스크레벨","최종판단"}
    assert required_cols.issubset(df_report.columns), f"리포트 컬럼 누락: {required_cols - set(df_report.columns)}"

    # --- pick_promising_by_theme_once ---
    df_pick = pick_promising_by_theme_once(THEME_ROWS, THEME_STOCKS, top_n=3)
    assert isinstance(df_pick, pd.DataFrame), "pick_promising 반환형 오류"
    if not df_pick.empty:
        for col in ["종목명", "티커", "테마", "등락률(%)", "뉴스빈도", "AI점수"]:
            assert col in df_pick.columns, f"추천 결과 컬럼 누락: {col}"

    # --- 저장 기능 테스트 ---
    paths = save_report_and_picks(THEME_ROWS, THEME_STOCKS, out_dir="reports_test", top_n=3, prefix="unittest")
    for k in ["report_csv","report_json","picks_csv","picks_json"]:
        assert os.path.isfile(paths[k]), f"파일 저장 실패: {k} -> {paths[k]}"

    print("[ai_logic V3.7.1+R] ✅ All self-tests passed. Saved:")
    for k, v in paths.items():
        print(f" - {k}: {v}")
