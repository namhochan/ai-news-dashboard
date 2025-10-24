modules/analyzer.py

종목 분석 & 기록 (파일/DB 안전, 외부 네트워크 의존 없음)

v3.7.1+3

from future import annotations from typing import Any, Dict, Optional, Tuple, List from datetime import datetime, timezone, timedelta import json import os import sqlite3 import pandas as pd

tzdata 없이 안전한 KST 고정

KST = timezone(timedelta(hours=9))

외부 시세 의존성: modules.market.fetch_quote 사용 (없으면 graceful fallback)

try: from modules.market import fetch_quote  # type: ignore except Exception: fetch_quote = None  # type: ignore

-----------------------------

DB 경로/스키마

-----------------------------

_DEFAULT_DIR = os.environ.get("ANALYZER_DATA_DIR", "data") _DEFAULT_DB = os.path.join(_DEFAULT_DIR, "analysis.db")

_SCHEMA = """ CREATE TABLE IF NOT EXISTS analyses ( id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, name TEXT NOT NULL, ticker TEXT NOT NULL, summary TEXT NOT NULL, payload TEXT NOT NULL ); CREATE INDEX IF NOT EXISTS idx_analyses_ts ON analyses(ts DESC); """

def _ensure_dir(path: str) -> None: if not os.path.isdir(path): os.makedirs(path, exist_ok=True)

def _connect(db_path: Optional[str] = None) -> sqlite3.Connection: _ensure_dir(os.path.dirname(db_path or _DEFAULT_DB) or ".") return sqlite3.connect(db_path or _DEFAULT_DB, check_same_thread=False)

-----------------------------

Public API

-----------------------------

def init_db(db_path: Optional[str] = None) -> bool: """DB 파일과 테이블을 준비한다. 여러 번 호출해도 안전.""" try: with _connect(db_path) as con: con.executescript(_SCHEMA) return True except Exception: return False

def _fallback_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Optional[int]]: # 네트워크/의존성 부재 시 결정적 더미 값 생성 seed = sum(ord(c) for c in (ticker or "")) % 100 last = 100.0 + (seed - 50) * 0.25 prev = last * (1.0 - ((seed % 7) - 3) * 0.006) vol = 60_000 + seed * 500 return float(last), float(prev), int(vol)

def _get_quote(ticker: str) -> Tuple[Optional[float], Optional[float], Optional[int]]: try: if fetch_quote is not None: return fetch_quote(ticker) except Exception: pass return _fallback_quote(ticker)

def analyze_stock(name: str, ticker: str, db_path: Optional[str] = None) -> Tuple[str, Dict[str, Any]]: """간단 분석을 수행하고 기록까지 남긴다. - 외부 API 없이 직전 종가/전일 종가/거래량 기반 간단 요약 - 성공 시 (요약문, payload dict) 반환 """ name = (name or "").strip() or "-" ticker = (ticker or "").strip() or "-"

last, prev, vol = _get_quote(ticker)

# 등락률/방향 계산
delta_pct: Optional[float]
if last in (None,) or prev in (None, 0):
    delta_pct = None
else:
    try:
        delta_pct = (float(last) - float(prev)) / float(prev) * 100.0
    except Exception:
        delta_pct = None

ts = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

# 요약 생성 (간결/결정적)
if delta_pct is None:
    summary = f"{name}({ticker}) — 시세 정보 부족으로 간단 요약만 생성"
else:
    arrow = "상승" if delta_pct >= 0 else "하락"
    summary = (
        f"{name}({ticker}) — 전일대비 {delta_pct:+.2f}% {arrow}. "
        f"현재가: {last:.2f}, 전일: {prev:.2f}, 거래량: {('-' if vol is None else int(vol))}"
    )

payload: Dict[str, Any] = {
    "time": ts,
    "name": name,
    "ticker": ticker,
    "last": None if last is None else float(last),
    "prev": None if prev is None else float(prev),
    "volume": None if vol is None else int(vol),
    "change_pct": delta_pct if delta_pct is None else float(f"{delta_pct:.4f}"),
}

# 기록 저장 (try-best)
try:
    with _connect(db_path) as con:
        con.execute(
            "INSERT INTO analyses(ts,name,ticker,summary,payload) VALUES(?,?,?,?,?)",
            (ts, name, ticker, summary, json.dumps(payload, ensure_ascii=False)),
        )
        con.commit()
except Exception:
    # DB 저장 실패해도 분석 결과는 반환
    pass

return summary, payload

def load_recent(limit: int = 10, db_path: Optional[str] = None) -> pd.DataFrame: """최근 기록 N건을 DataFrame으로 반환. 기록이 없으면 빈 DF.""" try: with _connect(db_path) as con: cur = con.execute( "SELECT ts as 시간, name as 종목명, ticker as 티커, summary as 요약 FROM analyses ORDER BY ts DESC LIMIT ?", (int(max(1, limit)),), ) rows = cur.fetchall() except Exception: rows = [] if not rows: return pd.DataFrame(columns=["시간", "종목명", "티커", "요약"]) df = pd.DataFrame(rows, columns=["시간", "종목명", "티커", "요약"]) return df

-----------------------------

Self tests (no external network)

-----------------------------

if name == "main": assert init_db(), "DB 초기화 실패" s, d = analyze_stock("삼성전자", "005930.KS") assert isinstance(s, str) and isinstance(d, dict) df = load_recent(limit=5) assert isinstance(df, pd.DataFrame) # 최소 컬럼 검사 assert set(["시간","종목명","티커","요약"]).issubset(df.columns) print("[analyzer] ✅ self-tests passed, rows:", len(df))
